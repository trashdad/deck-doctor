/**
 * FIXTURE DATA for /dev/ui-kit — 16 real cards copied by id from data/cards.json
 * (Scryfall ids + image URLs). Nothing here is invented, but note:
 *   - `mechanic_tags` / `wincon` are FIXTURE annotations (the real values live in the
 *     scoring DB and reach the UI via the API); they only steer lane placement here.
 *   - `ier` is null everywhere; gallery pills are passed explicitly as fixture text.
 * Regenerate with the node snippet in docs/plans (see MIGRATION.md) if cards.json changes.
 */
import type { Card } from "@/lib/types";

export const krenko: Card = {
  "id": "824b2d73-2151-4e5e-9f05-8f63e2bdcaa9",
  "name": "Krenko, Mob Boss",
  "cmc": 4,
  "type_line": "Legendary Creature — Goblin Warrior",
  "oracle_text": "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.",
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "power": "3",
  "toughness": "3",
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/8/2/824b2d73-2151-4e5e-9f05-8f63e2bdcaa9.jpg?1783909065"
  },
  "ier": null,
  "mechanic_tags": [
    "token_created"
  ]
};

export const solRing: Card = {
  "id": "8ae6d023-2945-47f1-bc9f-f9c5ff9f5282",
  "name": "Sol Ring",
  "cmc": 1,
  "type_line": "Artifact",
  "oracle_text": "{T}: Add {C}{C}.",
  "colors": [],
  "color_identity": [],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/8/a/8ae6d023-2945-47f1-bc9f-f9c5ff9f5282.jpg?1783903504"
  },
  "ier": null,
  "mechanic_tags": [
    "ramp"
  ]
};

export const arcaneSignet: Card = {
  "id": "dc04f5a7-94cf-417d-a09b-972a1ca97ec8",
  "name": "Arcane Signet",
  "cmc": 2,
  "type_line": "Artifact",
  "oracle_text": "{T}: Add one mana of any color in your commander's color identity.",
  "colors": [],
  "color_identity": [],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/d/c/dc04f5a7-94cf-417d-a09b-972a1ca97ec8.jpg?1783903505"
  },
  "ier": null,
  "mechanic_tags": [
    "ramp"
  ]
};

export const dragonTempest: Card = {
  "id": "39ac7ad0-e570-4209-988c-7c0f9b9d2004",
  "name": "Dragon Tempest",
  "cmc": 2,
  "type_line": "Enchantment",
  "oracle_text": "Whenever a creature you control with flying enters, it gains haste until end of turn.\nWhenever a Dragon you control enters, it deals X damage to any target, where X is the number of Dragons you control.",
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/3/9/39ac7ad0-e570-4209-988c-7c0f9b9d2004.jpg?1783907139"
  },
  "ier": null,
  "mechanic_tags": []
};

export const isochron: Card = {
  "id": "6e8beae7-f1ca-4f21-ada4-2e625657571b",
  "name": "Isochron Scepter",
  "cmc": 2,
  "type_line": "Artifact",
  "oracle_text": "Imprint — When this artifact enters, you may exile an instant card with mana value 2 or less from your hand.\n{2}, {T}: You may copy the exiled card. If you do, you may cast the copy without paying its mana cost.",
  "colors": [],
  "color_identity": [],
  "power": null,
  "toughness": null,
  "keywords": [
    "Imprint"
  ],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/6/e/6e8beae7-f1ca-4f21-ada4-2e625657571b.jpg?1783905107"
  },
  "ier": null,
  "mechanic_tags": []
};

export const hullbreaker: Card = {
  "id": "08fd6904-c497-40de-b3cf-a427e5bed264",
  "name": "Hullbreaker Horror",
  "cmc": 7,
  "type_line": "Creature — Kraken Horror",
  "oracle_text": "Flash\nThis spell can't be countered.\nWhenever you cast a spell, choose up to one —\n• Return target spell you don't control to its owner's hand.\n• Return target nonland permanent to its owner's hand.",
  "colors": [
    "U"
  ],
  "color_identity": [
    "U"
  ],
  "power": "7",
  "toughness": "8",
  "keywords": [
    "Flash"
  ],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/0/8/08fd6904-c497-40de-b3cf-a427e5bed264.jpg?1783905158"
  },
  "ier": null,
  "mechanic_tags": []
};

export const crimsonWisps: Card = {
  "id": "1e32a5c0-7ad3-453e-8980-7c8e607f47ee",
  "name": "Crimson Wisps",
  "cmc": 1,
  "type_line": "Instant",
  "oracle_text": "Target creature becomes red and gains haste until end of turn. (It can attack and {T} this turn.)\nDraw a card.",
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/1/e/1e32a5c0-7ad3-453e-8980-7c8e607f47ee.jpg?1783908693"
  },
  "ier": null,
  "mechanic_tags": [
    "card_draw"
  ]
};

export const urDragon: Card = {
  "id": "4de700d8-2a0c-439e-b8c9-8663fa813ac7",
  "name": "The Ur-Dragon",
  "cmc": 9,
  "type_line": "Legendary Creature — Dragon Avatar",
  "oracle_text": "Eminence — As long as The Ur-Dragon is in the command zone or on the battlefield, other Dragon spells you cast cost {1} less to cast.\nFlying\nWhenever one or more Dragons you control attack, draw that many cards, then you may put a permanent card from your hand onto the battlefield.",
  "colors": [
    "B",
    "G",
    "R",
    "U",
    "W"
  ],
  "color_identity": [
    "B",
    "G",
    "R",
    "U",
    "W"
  ],
  "power": "10",
  "toughness": "10",
  "keywords": [
    "Flying",
    "Eminence"
  ],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/4/d/4de700d8-2a0c-439e-b8c9-8663fa813ac7.jpg?1783905642"
  },
  "ier": null,
  "mechanic_tags": []
};

export const rhystic: Card = {
  "id": "cd212de7-25f6-4b3b-a35b-df7d87fe205b",
  "name": "Rhystic Study",
  "cmc": 3,
  "type_line": "Enchantment",
  "oracle_text": "Whenever an opponent casts a spell, you may draw a card unless that player pays {1}.",
  "colors": [
    "U"
  ],
  "color_identity": [
    "U"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/c/d/cd212de7-25f6-4b3b-a35b-df7d87fe205b.jpg?1783906385"
  },
  "ier": null,
  "mechanic_tags": [
    "card_draw"
  ]
};

export const skullclamp: Card = {
  "id": "4e5d5649-3e30-4aca-80f8-5a7522d366da",
  "name": "Skullclamp",
  "cmc": 1,
  "type_line": "Artifact — Equipment",
  "oracle_text": "Equipped creature gets +1/-1.\nWhenever equipped creature dies, draw two cards.\nEquip {1}",
  "colors": [],
  "color_identity": [],
  "power": null,
  "toughness": null,
  "keywords": [
    "Equip"
  ],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/4/e/4e5d5649-3e30-4aca-80f8-5a7522d366da.jpg?1783906237"
  },
  "ier": null,
  "mechanic_tags": [
    "card_draw"
  ]
};

export const bombardment: Card = {
  "id": "18a9fb7b-780c-46c7-9a5f-f9abb3c353df",
  "name": "Goblin Bombardment",
  "cmc": 2,
  "type_line": "Enchantment",
  "oracle_text": "Sacrifice a creature: This enchantment deals 1 damage to any target.",
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/1/8/18a9fb7b-780c-46c7-9a5f-f9abb3c353df.jpg?1783904248"
  },
  "ier": null,
  "mechanic_tags": []
};

export const blasphemous: Card = {
  "id": "175eb155-7262-4c2e-85c3-e0cc9be855e5",
  "name": "Blasphemous Act",
  "cmc": 9,
  "type_line": "Sorcery",
  "oracle_text": "This spell costs {1} less to cast for each creature on the battlefield.\nBlasphemous Act deals 13 damage to each creature.",
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/1/7/175eb155-7262-4c2e-85c3-e0cc9be855e5.jpg?1783903777"
  },
  "ier": null,
  "mechanic_tags": [
    "board_wipe"
  ]
};

export const bolt: Card = {
  "id": "bde26955-6de3-4212-9e1a-5e11f73ebf44",
  "name": "Lightning Bolt",
  "cmc": 1,
  "type_line": "Instant",
  "oracle_text": "Lightning Bolt deals 3 damage to any target.",
  "colors": [
    "R"
  ],
  "color_identity": [
    "R"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/b/d/bde26955-6de3-4212-9e1a-5e11f73ebf44.jpg?1783903996"
  },
  "ier": null,
  "mechanic_tags": [
    "removal"
  ]
};

export const rift: Card = {
  "id": "7037f57a-ca89-41bd-bf7f-2f54593c0f48",
  "name": "Cyclonic Rift",
  "cmc": 2,
  "type_line": "Instant",
  "oracle_text": "Return target nonland permanent you don't control to its owner's hand.\nOverload {6}{U} (You may cast this spell for its overload cost. If you do, change \"target\" in its text to \"each.\")",
  "colors": [
    "U"
  ],
  "color_identity": [
    "U"
  ],
  "power": null,
  "toughness": null,
  "keywords": [
    "Overload"
  ],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/7/0/7037f57a-ca89-41bd-bf7f-2f54593c0f48.jpg?1783903929"
  },
  "ier": null,
  "mechanic_tags": [
    "board_wipe"
  ]
};

export const mountain: Card = {
  "id": "2a7b2779-92dd-455d-920f-684276608244",
  "name": "Mountain",
  "cmc": 0,
  "type_line": "Basic Land — Mountain",
  "oracle_text": "({T}: Add {R}.)",
  "colors": [],
  "color_identity": [
    "R"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/2/a/2a7b2779-92dd-455d-920f-684276608244.jpg?1783903501"
  },
  "ier": null,
  "mechanic_tags": []
};

export const swords: Card = {
  "id": "68ec2aed-7662-48ae-ab25-04f74ece1e41",
  "name": "Swords to Plowshares",
  "cmc": 1,
  "type_line": "Instant",
  "oracle_text": "Exile target creature. Its controller gains life equal to its power.",
  "colors": [
    "W"
  ],
  "color_identity": [
    "W"
  ],
  "power": null,
  "toughness": null,
  "keywords": [],
  "image_uris": {
    "normal": "https://cards.scryfall.io/normal/front/6/8/68ec2aed-7662-48ae-ab25-04f74ece1e41.jpg?1783903796"
  },
  "ier": null,
  "mechanic_tags": [
    "removal"
  ]
};

export const FIXTURE_CARDS: Card[] = [krenko, solRing, arcaneSignet, dragonTempest, isochron, hullbreaker, crimsonWisps, urDragon, rhystic, skullclamp, bombardment, blasphemous, bolt, rift, mountain, swords];
