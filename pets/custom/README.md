# Custom Buddy Pets

Buddy keeps imported custom pets here.

Use the bridge to manage them:

```sh
python3 bridge/buddy.py pet import --id my-pet ./my-codex-spritesheet.webp
python3 bridge/buddy.py pet list
python3 bridge/buddy.py pet set --pet-id my-pet
python3 bridge/buddy.py pet remove --id my-pet
```

Custom animated pets should match the Codex desktop spritesheet layout:

- `8` columns
- `9` rows
- state rows for `idle`, `running`, `running-left`, `running-right`, `waiting`, `review`, `failed`, `jumping`, `waving`
