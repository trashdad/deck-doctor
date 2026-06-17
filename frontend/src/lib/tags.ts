/**
 * Tag display metadata — label, group, and color for each semantic tag.
 * Source of truth: scoring/tag_taxonomy.py TAG_META
 */

export interface TagMeta {
  label: string;
  group: TagGroup;
  color: string;
}

export type TagGroup =
  | "Perm Types"
  | "Triggers"
  | "Effects"
  | "Counters"
  | "Targets"
  | "Keywords"
  | "Replacement";

export const TAG_GROUPS: TagGroup[] = [
  "Perm Types",
  "Triggers",
  "Effects",
  "Counters",
  "Keywords",
  "Targets",
  "Replacement",
];

const META: Record<string, TagMeta> = {
  // Perm Types
  "perm:creature":     { label: "creature",      group: "Perm Types", color: "#22c55e" },
  "perm:artifact":     { label: "artifact",      group: "Perm Types", color: "#9aa0a6" },
  "perm:enchantment":  { label: "enchantment",   group: "Perm Types", color: "#a855f7" },
  "perm:land":         { label: "land",           group: "Perm Types", color: "#ffd24a" },
  "perm:planeswalker": { label: "planeswalker",   group: "Perm Types", color: "#3b82f6" },
  "perm:battle":       { label: "battle",         group: "Perm Types", color: "#f97316" },
  "perm:instant":      { label: "instant",        group: "Perm Types", color: "#3b82f6" },
  "perm:sorcery":      { label: "sorcery",        group: "Perm Types", color: "#f97316" },
  "perm:token":        { label: "token",          group: "Perm Types", color: "#22c55e" },
  // Triggers
  "t:etb":                 { label: "enters battlefield",  group: "Triggers",    color: "#ef4444" },
  "t:creature_dies":       { label: "creature dies",       group: "Triggers",    color: "#ef4444" },
  "t:leaves":              { label: "leaves battlefield",  group: "Triggers",    color: "#ef4444" },
  "t:permanent_destroyed": { label: "permanent destroyed", group: "Triggers",    color: "#ef4444" },
  "t:enters_graveyard":    { label: "enters graveyard",    group: "Triggers",    color: "#ef4444" },
  "t:attacks":             { label: "attacks",             group: "Triggers",    color: "#ef4444" },
  "t:blocks":              { label: "blocks",              group: "Triggers",    color: "#ef4444" },
  "t:blocked":             { label: "becomes blocked",     group: "Triggers",    color: "#ef4444" },
  "t:combat_damage":       { label: "deals combat damage", group: "Triggers",    color: "#ef4444" },
  "t:damage_dealt":        { label: "damage dealt",        group: "Triggers",    color: "#ef4444" },
  "t:draw":                { label: "card drawn",          group: "Triggers",    color: "#ef4444" },
  "t:discard":             { label: "card discarded",      group: "Triggers",    color: "#ef4444" },
  "t:cast_spell":          { label: "spell cast",          group: "Triggers",    color: "#ef4444" },
  "t:counter_placed":      { label: "counter placed",      group: "Triggers",    color: "#ef4444" },
  "t:counter_removed":     { label: "counter removed",     group: "Triggers",    color: "#ef4444" },
  "t:sacrifice":           { label: "sacrificed",          group: "Triggers",    color: "#ef4444" },
  "t:life_gained":         { label: "life gained",         group: "Triggers",    color: "#ef4444" },
  "t:life_lost":           { label: "life lost",           group: "Triggers",    color: "#ef4444" },
  "t:exiled":              { label: "permanent exiled",    group: "Triggers",    color: "#ef4444" },
  "t:tapped":              { label: "permanent tapped",    group: "Triggers",    color: "#ef4444" },
  "t:untap":               { label: "untaps",              group: "Triggers",    color: "#ef4444" },
  "t:targeted":            { label: "targeted",            group: "Triggers",    color: "#ef4444" },
  "t:cycle":               { label: "cycling",             group: "Triggers",    color: "#ef4444" },
  "t:upkeep":              { label: "upkeep",              group: "Triggers",    color: "#ef4444" },
  "t:end_step":            { label: "end step",            group: "Triggers",    color: "#ef4444" },
  "t:combat":              { label: "begin combat",        group: "Triggers",    color: "#ef4444" },
  "t:end_of_combat":       { label: "end of combat",       group: "Triggers",    color: "#ef4444" },
  "t:main_phase":          { label: "main phase",          group: "Triggers",    color: "#ef4444" },
  "t:token_created":       { label: "token created",       group: "Triggers",    color: "#ef4444" },
  "t:landfall":            { label: "land enters",         group: "Triggers",    color: "#ef4444" },
  "t:activated_ability":   { label: "ability activated",   group: "Triggers",    color: "#ef4444" },
  "t:proliferate_trigger": { label: "proliferate trigger", group: "Triggers",    color: "#ef4444" },
  "t:transform":           { label: "transforms",          group: "Triggers",    color: "#ef4444" },
  "t:mana_tapped":         { label: "tapped for mana",     group: "Triggers",    color: "#ef4444" },
  "t:mana_ability":        { label: "mana ability",        group: "Triggers",    color: "#ef4444" },
  "t:mutate":              { label: "mutates",             group: "Triggers",    color: "#ef4444" },
  "t:graveyard_leave":     { label: "leaves graveyard",    group: "Triggers",    color: "#ef4444" },
  "t:turned_face_up":      { label: "turned face up",      group: "Triggers",    color: "#ef4444" },
  // Effects
  "e:draw":          { label: "draw cards",       group: "Effects",     color: "#3b82f6" },
  "e:discard":       { label: "discard",          group: "Effects",     color: "#3b82f6" },
  "e:damage":        { label: "deal damage",      group: "Effects",     color: "#f97316" },
  "e:gain_life":     { label: "gain life",        group: "Effects",     color: "#22c55e" },
  "e:lose_life":     { label: "lose life",        group: "Effects",     color: "#f97316" },
  "e:destroy":       { label: "destroy",          group: "Effects",     color: "#a855f7" },
  "e:exile":         { label: "exile",            group: "Effects",     color: "#a855f7" },
  "e:bounce":        { label: "return to hand",   group: "Effects",     color: "#3b82f6" },
  "e:board_wipe":    { label: "board wipe",       group: "Effects",     color: "#a855f7" },
  "e:sacrifice":     { label: "sacrifice",        group: "Effects",     color: "#a855f7" },
  "e:create_token":  { label: "create tokens",    group: "Effects",     color: "#22c55e" },
  "e:populate":      { label: "populate",         group: "Effects",     color: "#22c55e" },
  "e:add_counter":   { label: "put counters",     group: "Effects",     color: "#ffd24a" },
  "e:remove_counter":{ label: "remove counters",  group: "Effects",     color: "#ffd24a" },
  "e:proliferate":   { label: "proliferate",      group: "Effects",     color: "#ffd24a" },
  "e:tutor":         { label: "search library",   group: "Effects",     color: "#3b82f6" },
  "e:mill":          { label: "mill",             group: "Effects",     color: "#9aa0a6" },
  "e:reanimate":     { label: "reanimate",        group: "Effects",     color: "#a855f7" },
  "e:surveil":       { label: "surveil",          group: "Effects",     color: "#3b82f6" },
  "e:scry":          { label: "scry",             group: "Effects",     color: "#3b82f6" },
  "e:counter_spell": { label: "counter spell",    group: "Effects",     color: "#3b82f6" },
  "e:fight":         { label: "fight",            group: "Effects",     color: "#f97316" },
  "e:tap":           { label: "tap",              group: "Effects",     color: "#9aa0a6" },
  "e:untap":         { label: "untap",            group: "Effects",     color: "#9aa0a6" },
  "e:transform":     { label: "transform",        group: "Effects",     color: "#ffd24a" },
  "e:copy":          { label: "copy",             group: "Effects",     color: "#a855f7" },
  "e:steal":         { label: "steal control",    group: "Effects",     color: "#a855f7" },
  "e:mana":          { label: "add mana",         group: "Effects",     color: "#22c55e" },
  "e:extra_turn":    { label: "extra turn",       group: "Effects",     color: "#ffd24a" },
  "e:pump":          { label: "pump/buff",        group: "Effects",     color: "#ffd24a" },
  "e:investigate":   { label: "investigate",      group: "Effects",     color: "#ffd24a" },
  "e:discover":      { label: "discover",         group: "Effects",     color: "#ffd24a" },
  "e:explore":       { label: "explore",          group: "Effects",     color: "#22c55e" },
  "e:phase_out":     { label: "phase out",        group: "Effects",     color: "#9aa0a6" },
  "e:regenerate":    { label: "regenerate",       group: "Effects",     color: "#22c55e" },
  "e:flip_coin":     { label: "flip coin",        group: "Effects",     color: "#9aa0a6" },
  "e:roll_dice":     { label: "roll dice",        group: "Effects",     color: "#9aa0a6" },
  "e:venture":       { label: "venture",          group: "Effects",     color: "#ffd24a" },
  "e:monarch":       { label: "the monarch",      group: "Effects",     color: "#ffd24a" },
  // Counters
  "c:plus1":     { label: "+1/+1 counter",   group: "Counters",    color: "#22c55e" },
  "c:minus1":    { label: "−1/−1 counter",   group: "Counters",    color: "#ef4444" },
  "c:poison":    { label: "poison counter",  group: "Counters",    color: "#a855f7" },
  "c:loyalty":   { label: "loyalty counter", group: "Counters",    color: "#3b82f6" },
  "c:experience":{ label: "experience",      group: "Counters",    color: "#ffd24a" },
  "c:charge":    { label: "charge counter",  group: "Counters",    color: "#9aa0a6" },
  "c:oil":       { label: "oil counter",     group: "Counters",    color: "#9aa0a6" },
  "c:time":      { label: "time counter",    group: "Counters",    color: "#ffd24a" },
  "c:blight":    { label: "blight counter",  group: "Counters",    color: "#a855f7" },
  "c:shield":    { label: "shield counter",  group: "Counters",    color: "#22c55e" },
  "c:lore":      { label: "lore counter",    group: "Counters",    color: "#ffd24a" },
  "c:storage":   { label: "storage counter", group: "Counters",    color: "#9aa0a6" },
  "c:quest":     { label: "quest counter",   group: "Counters",    color: "#ffd24a" },
  // Keywords
  "k:flying":        { label: "flying",        group: "Keywords",    color: "#00eeff" },
  "k:trample":       { label: "trample",       group: "Keywords",    color: "#00eeff" },
  "k:deathtouch":    { label: "deathtouch",    group: "Keywords",    color: "#00eeff" },
  "k:lifelink":      { label: "lifelink",      group: "Keywords",    color: "#00eeff" },
  "k:menace":        { label: "menace",        group: "Keywords",    color: "#00eeff" },
  "k:vigilance":     { label: "vigilance",     group: "Keywords",    color: "#00eeff" },
  "k:haste":         { label: "haste",         group: "Keywords",    color: "#00eeff" },
  "k:first_strike":  { label: "first strike",  group: "Keywords",    color: "#00eeff" },
  "k:double_strike": { label: "double strike", group: "Keywords",    color: "#00eeff" },
  "k:hexproof":      { label: "hexproof",      group: "Keywords",    color: "#00eeff" },
  "k:indestructible":{ label: "indestructible", group: "Keywords",    color: "#00eeff" },
  "k:ward":          { label: "ward",          group: "Keywords",    color: "#00eeff" },
  "k:infect":        { label: "infect",        group: "Keywords",    color: "#00eeff" },
  "k:wither":        { label: "wither",        group: "Keywords",    color: "#00eeff" },
  "k:toxic":         { label: "toxic",         group: "Keywords",    color: "#00eeff" },
  "k:proliferate":   { label: "proliferate",   group: "Keywords",    color: "#00eeff" },
  "k:flash":         { label: "flash",         group: "Keywords",    color: "#00eeff" },
  "k:reach":         { label: "reach",         group: "Keywords",    color: "#00eeff" },
  "k:convoke":       { label: "convoke",       group: "Keywords",    color: "#00eeff" },
  "k:delve":         { label: "delve",         group: "Keywords",    color: "#00eeff" },
  "k:flashback":     { label: "flashback",     group: "Keywords",    color: "#00eeff" },
  "k:equip":         { label: "equip",         group: "Keywords",    color: "#00eeff" },
  "k:cycling":       { label: "cycling",       group: "Keywords",    color: "#00eeff" },
  "k:kicker":        { label: "kicker",        group: "Keywords",    color: "#00eeff" },
  "k:persist":       { label: "persist",       group: "Keywords",    color: "#00eeff" },
  "k:undying":       { label: "undying",       group: "Keywords",    color: "#00eeff" },
  "k:modular":       { label: "modular",       group: "Keywords",    color: "#00eeff" },
  "k:graft":         { label: "graft",         group: "Keywords",    color: "#00eeff" },
  "k:evolve":        { label: "evolve",        group: "Keywords",    color: "#00eeff" },
  "k:extort":        { label: "extort",        group: "Keywords",    color: "#00eeff" },
  "k:prowess":       { label: "prowess",       group: "Keywords",    color: "#00eeff" },
  "k:mutate":        { label: "mutate",        group: "Keywords",    color: "#00eeff" },
  "k:escape":        { label: "escape",        group: "Keywords",    color: "#00eeff" },
  "k:cascade":       { label: "cascade",       group: "Keywords",    color: "#00eeff" },
  "k:storm":         { label: "storm",         group: "Keywords",    color: "#00eeff" },
  "k:suspend":       { label: "suspend",       group: "Keywords",    color: "#00eeff" },
  "k:dredge":        { label: "dredge",        group: "Keywords",    color: "#00eeff" },
  "k:madness":       { label: "madness",       group: "Keywords",    color: "#00eeff" },
  "k:landfall":      { label: "landfall",      group: "Keywords",    color: "#00eeff" },
  "k:ninjutsu":      { label: "ninjutsu",      group: "Keywords",    color: "#00eeff" },
  // Targets
  "tgt:self":        { label: "targets self",      group: "Targets",    color: "#9aa0a6" },
  "tgt:opponent":    { label: "targets opponent",  group: "Targets",    color: "#ef4444" },
  "tgt:any_player":  { label: "any player",        group: "Targets",    color: "#9aa0a6" },
  "tgt:each_player": { label: "each player",       group: "Targets",    color: "#9aa0a6" },
  "tgt:creature":    { label: "targets creature",  group: "Targets",    color: "#9aa0a6" },
  // Replacement
  "r:replace_draw":     { label: "replaces draws",     group: "Replacement", color: "#9aa0a6" },
  "r:replace_death":    { label: "replaces death",     group: "Replacement", color: "#9aa0a6" },
  "r:replace_damage":   { label: "redirects damage",   group: "Replacement", color: "#9aa0a6" },
  "r:replace_etb":      { label: "enters differently", group: "Replacement", color: "#9aa0a6" },
  "r:replace_counters": { label: "modifies counters",  group: "Replacement", color: "#9aa0a6" },
  "r:replace_mill":     { label: "replaces mill",      group: "Replacement", color: "#9aa0a6" },
  "r:replace_discard":  { label: "replaces discard",   group: "Replacement", color: "#9aa0a6" },
};

export function getTagMeta(tag: string): TagMeta {
  return (
    META[tag] ?? {
      label: tag.replace(/^[a-z]+:/, "").replace(/_/g, " "),
      group: "Effects" as TagGroup,
      color: "#9aa0a6",
    }
  );
}

export function groupTagsByCategory(tags: string[]): Record<TagGroup, string[]> {
  const out: Record<TagGroup, string[]> = {
    "Perm Types": [],
    Triggers: [],
    Effects: [],
    Counters: [],
    Keywords: [],
    Targets: [],
    Replacement: [],
  };
  for (const tag of tags) {
    const m = getTagMeta(tag);
    out[m.group].push(tag);
  }
  return out;
}
