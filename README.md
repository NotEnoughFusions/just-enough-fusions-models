# Just Enough Fusions community models

3D models for fused Pokémon in the Cobblemon: Just Enough Fusions mod. Everything published here is downloaded by the mod automatically, and players pick a look when they fuse.

## Submitting a model

1. Make the model in [Blockbench](https://www.blockbench.net/) as a Bedrock Entity, the same as Cobblemon models. Name the head bone `head` so it can look around.
2. If it can be ridden, add locators called `seat_1`, `seat_2` and so on where riders sit, inside the bone they should move with. If you don't, the bot puts seats on top of the body for you.
3. Zip up the `.geo.json` and the texture `.png`, plus an `.animation.json` and a `_glow.png` if you have them.
4. [Open a submission](../../issues/new?template=submit-model.yml), pick the fusion type and drag the zip in. For two Pokémon, fill in the head and body. For a triple fusion, fill in the head and body and the core. For Omnieon, leave the species empty.

A bot checks the files within a minute or so and replies on the issue. If something's wrong, fix it and edit the issue, and it gets checked again.

You can try a model in your own game before submitting it with the mod's test mode (see the mod's README).

Animation names the mod uses: `idle`, `walk`, `sleep`, `battle_idle`, `faint`, `cry` and `blink`, plus `fly` and `hover` for moving and staying still in the air (otherwise `walk` and `idle` are used). Anything called `quirk_something` plays now and then while idle, and `battle_quirk_something` does the same in battle, up to 6 of them.

## When models go live

Models from people in `trusted.txt` go live straight away. Everyone else's only show for players who've turned on unreviewed models, until a moderator approves them. A model with 3 open reports gets hidden until a moderator looks at it.

## Bug reports

The Report bug button in the mod's Fusion Handbook opens the bug report form here, with the player's versions and mods already filled in. Those issues get the `bug` label, and the model bot leaves them alone. If the label doesn't exist yet, run **Actions → First-time setup** again.

## Moderating

The repo owner and collaborators can comment these on any issue:

| Command | What it does |
|---|---|
| `/approve` or `/approve model-id` | Makes a model live for everyone |
| `/hide model-id` | Hides a model |
| `/delete model-id` | Removes a model completely |
| `/trust github-name` | That person's future models go live without review |

On a submission issue, `/approve`, `/hide` and `/delete` work without the id.
