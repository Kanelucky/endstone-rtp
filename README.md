# RTP

A simple random teleport plugin for [Endstone](https://github.com/EndstoneMC/endstone).

Use `/rtp` to teleport to a random location around your current position.

## Configuration (config.toml)

```toml
radius = 1000
blacklist_blocks = [
    "minecraft:water",
    "minecraft:lava"
]
max_attempts = 10
[messages]
invalid-sender = "Only players can use this command!"
already-have-rtp-request = "You already have an RTP request!"
could-not-find-safe-loc = "Could not find a safe location after {max_attempts} attempts!"
loading-destination-chunks = "§eLoading destination chunks..."
teleport = "§aTeleported to {x}, {y}, {z}"
chunk-loading-timed-out = "Chunk loading timed out!"
failed-to-create-ticking-area = "Failed to create ticking area!"
failed-to-load-next-loc = "Failed to load the next location!"
unknown-dimension = "Unknown dimension!"
```

## Commands

| Command | Description | Permission      |
|---|---|-----------------|
| `/rtp` | Teleport to a random location | `rtp.command.rtp` |

Command /rtp 

## License

This project is licensed under MIT license. See [LICENSE](LICENSE) for more.