import random
import time

from endstone import ColorFormat, Player
from endstone.command import CommandSender, Command, CommandSenderWrapper
from endstone.event import ChunkLoadEvent, event_handler
from endstone.level import Location
from endstone.plugin import Plugin


class RTP(Plugin):
    api_version = "0.11"

    commands = {
        "rtp": {
            "description": "Teleport to random location",
            "usages": ["/rtp"],
            "permissions": ["rtp.command.rtp"],
        }
    }

    permissions = {
        "rtp.command.rtp": {
            "description": "Allow users to use the /rtp command.",
            "default": True,
        }
    }

    max_attempts = 10

    def __init__(self):
        super().__init__()
        self.rtp_jobs = {}
        self.rtp_task = None
        self.rtp_counter = 0

    def on_enable(self):
        self.save_default_config()
        self.register_events(self)
        self.logger.info(f"{ColorFormat.GREEN}Enabled successfully!")

    def normalize_dimension(self, raw):
        aliases = {
            "overworld": "overworld",
            "world": "overworld",
            "nether": "nether",
            "thenether": "nether",
            "end": "the_end",
            "theend": "the_end",
        }
        if not isinstance(raw, str):
            name = getattr(raw, "name", None)
            if name is None:
                dimension_type = getattr(raw, "type", None)
                name = getattr(dimension_type, "name", None)
            raw = name if name is not None else ""
        cleaned = (
            str(raw).lower()
            .replace("minecraft:", "")
            .replace("_", "")
            .replace(" ", "")
        )
        return aliases.get(cleaned)

    @event_handler
    def on_chunk_load(self, event: ChunkLoadEvent):
        chunk = event.chunk
        dimension_name = self.normalize_dimension(chunk.dimension)
        coord = (chunk.x, chunk.z)
        for job in self.rtp_jobs.values():
            if job["dimension_name"] != dimension_name:
                continue
            job["pending"].discard(coord)

    def start_rtp(self, sender: Player):
        location = sender.location
        dimension = location.dimension
        dimension_name = self.normalize_dimension(dimension)
        if dimension_name is None:
            sender.send_error_message(self.get_message_config("unknown-dimension"))
            return
        radius = self.config.get("radius")

        self.rtp_counter += 1

        job = {
            "sender": sender,
            "dimension": dimension,
            "dimension_name": dimension_name,

            "origin_x": location.block_x,
            "origin_z": location.block_z,

            "radius": radius,

            "x": 0,
            "z": 0,
            "pending": set(),

            "area_name": "",
            "area_created": False,

            "created_at": time.monotonic(),
            "settle_start": None,

            "attempts": 0,
        }

        key = id(sender)
        self.rtp_jobs[key] = job

        if not self.prepare_rtp_target(job):
            self.remove_rtp_job(key)
            sender.send_error_message(self.get_message_config("failed-to-create-ticking-area"))
            return

        sender.send_message(self.get_message_config("loading-destination-chunks"))

        if self.rtp_task is None:
            self.rtp_task = self.server.scheduler.run_task(
                self,
                self.tick_rtp,
                delay=1,
                period=1
            )

    def dispatch(self, command):
        errors = []
        sender = CommandSenderWrapper(
            self.server.command_sender,
            on_message=lambda message: None,
            on_error=errors.append
        )
        try:
            result = self.server.dispatch_command(sender, command)
            return result and not errors
        except Exception:
            return False

    def tick_rtp(self):
        now = time.monotonic()

        for key, job in list(self.rtp_jobs.items()):
            if now - job["created_at"] > 30:
                job["sender"].send_error_message(self.get_message_config("chunk-loading-timed-out"))
                self.remove_rtp_job(key)
                continue
            if job["pending"]:
                continue
            if job["settle_start"] is None:
                job["settle_start"] = now
                continue

            if now - job["settle_start"] < 2:
                continue

            sender = job["sender"]
            dimension = job["dimension"]

            try:
                highest_block = dimension.get_highest_block_at(
                    job["x"],
                    job["z"]
                )

                blacklist_blocks = list(self.config.get("blacklist_blocks"))

                if highest_block.type in blacklist_blocks:
                    job["attempts"] += 1

                    max_attempts = self.config.get("max_attempts")

                    if job["attempts"] >= max_attempts:
                        sender.send_error_message(
                            self.get_message_config(
                                "could-not-find-safe-loc".replace("{max_attempts}", str(max_attempts))
                            )
                        )
                        self.remove_rtp_job(key)
                        continue

                    if not self.prepare_rtp_target(job):
                        sender.send_error_message(
                            self.get_message_config("failed-to-load-next-loc")
                        )
                        self.remove_rtp_job(key)

                    continue

                destination = Location(
                    dimension,
                    job["x"] + 0.5,
                    highest_block.y + 1,
                    job["z"] + 0.5
                )

                sender.teleport(destination)

                sender.send_message(
                    self.get_message_config("teleport")
                    .replace("{x}", str(job['x']))
                    .replace("{y}", str(highest_block.y + 1))
                    .replace("{z}", str(job['z']))
                )

                self.remove_rtp_job(key)

            except Exception as e:
                self.logger.error(f"RTP error: {e}")
                self.remove_rtp_job(key)

        if not self.rtp_jobs and self.rtp_task is not None:
            self.rtp_task.cancel()
            self.rtp_task = None

    def remove_rtp_job(self, key):
        job = self.rtp_jobs.get(key)

        if job is None:
            return

        if job["area_created"]:
            self.dispatch(
                f"execute in {job['dimension_name']} run "
                f"tickingarea remove {job['area_name']}"
            )
            job["area_created"] = False

        self.rtp_jobs.pop(key, None)

    def prepare_rtp_target(self, job):
        if job["area_created"]:
            self.dispatch(
                f"execute in {job['dimension_name']} run "
                f"tickingarea remove {job['area_name']}"
            )
            job["area_created"] = False

        radius = job["radius"]

        x = job["origin_x"] + random.randint(-radius, radius)
        z = job["origin_z"] + random.randint(-radius, radius)

        chunk_x = x // 16
        chunk_z = z // 16

        coords = {
            (chunk_x + dx, chunk_z + dz)
            for dx in range(-1, 2)
            for dz in range(-1, 2)
        }

        dimension = job["dimension"]

        loaded = {
            (chunk.x, chunk.z)
            for chunk in dimension.loaded_chunks
        }

        job["x"] = x
        job["z"] = z
        job["pending"] = coords - loaded
        job["settle_start"] = None

        self.rtp_counter += 1
        job["area_name"] = f"rtp{self.rtp_counter}"

        if not job["pending"]:
            return True

        min_x = (chunk_x - 1) * 16
        min_z = (chunk_z - 1) * 16
        max_x = (chunk_x + 1) * 16 + 15
        max_z = (chunk_z + 1) * 16 + 15

        success = self.dispatch(
            f"execute in {job['dimension_name']} run "
            f"tickingarea add "
            f"{min_x} 0 {min_z} "
            f"{max_x} 0 {max_z} "
            f"{job['area_name']} true"
        )

        job["area_created"] = success
        return success

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name != "rtp":
            return False
        if not isinstance(sender, Player):
            sender.send_error_message(self.get_message_config("invalid-sender"))
            return True
        if id(sender) in self.rtp_jobs:
            sender.send_error_message(self.get_message_config("already-have-rtp-request"))
            return True
        self.start_rtp(sender)
        return True

    def get_message_config(self, option: str) -> str:
        return self.config.get("messages", {}).get(option)
