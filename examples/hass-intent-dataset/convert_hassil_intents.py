"""Convert OHF-Voice/intents (hassil) into an OVOS-INTENT-2 locale tree.

A demonstration of the OVOS-INTENT-1 ↔ hassil grammar overlap noted in
the architecture appendix: `[opt]`, `(a|b)`, `{slot}` and `<rule>` are
shared; the remaining hassil-specific forms have to be normalised:

    {list:slot}    → {slot}           (entity stored under the slot name)
    {@list}        → {list}           (compact capture form)
    {list:@cap}    → {cap}            (capture; treated as slot for matching)
    (a; b; c)      → (a b c|a c b|…)  (permutation → enumerated alternatives)
    (X)            → X                (single-branch group is a no-op)
    <rule>         → inlined          (rules expanded at use sites)

Lists become `.entity` files:

    values:   → literal value set
    range:    → enumerated integer set
    wildcard: → skipped (free-form slot at runtime)

Responses become `.dialog` after stripping hassil's Jinja; responses
with surviving Jinja (e.g. `state.domain` lookups) are skipped.

**Safety caps** — hassil grammars contain permutations and nested rule
references that combine into exponential string explosion. The script
guards against OOM with:

  * permutations of >5 elements (>120 orderings) collapse to a literal
    concatenation rather than enumerating;
  * rewritten samples larger than ``MAX_SAMPLE_BYTES`` are skipped;
  * each output file is written line-by-line with no full-corpus buffer;
  * if the output file already exists it is left alone (resumable).

This is an illustrative example, not a library util. The transformations
are textual and best-effort; a production tool would parse hassil
properly.

Run:
    pip install pyyaml
    git clone https://github.com/OHF-Voice/intents /tmp/ohf-intents
    python examples/convert_hassil_intents.py /tmp/ohf-intents en /tmp/ovos-locale
"""
from __future__ import annotations

import hashlib
import itertools
import re
import sys
import unicodedata
from pathlib import Path

import yaml

MAX_PERM_ELEMS = 5            # 5! = 120 orderings — anything above is collapsed
MAX_SAMPLE_BYTES = 4 * 1024   # skip rewritten samples larger than 4 KiB
MAX_SAMPLE_PATHS = 20000      # skip samples whose Cartesian expansion is too big
MAX_ENTITY_VALUES = 2000      # cap .entity file size (range lists)
MAX_RULE_BYTES = 16 * 1024    # skip inlining a rule whose body exceeds this
PROMOTE_RULE_THRESHOLD = 2    # any rule with ≥1 alt/opt becomes a `.voc` file
MAX_PROMOTED_VALUES = 2048    # don't promote a rule whose enumeration is huger

# Rules to force-promote to free-form capture slots even though their
# bodies contain `{slot}` references (so they can't be enumerated into a
# value set).
#
#   * `timer_duration` / `timer_start` inline into a 3-branch nested
#     grammar with multiple sub-slots and optionals — 10⁹-path samples.
#   * `area` / `name` / `floor` are slot wrappers that thread the actual
#     `{area}` / `{name}` / `{floor}` slots through optional article and
#     preposition syntax that varies dramatically across languages. In
#     German and Dutch in particular the inflection tables multiply with
#     every optional in the host template, accounting for ~65% of the
#     cartesian explosions in the audit log.
FORCE_PROMOTE: set[str] = {
    "timer_duration", "timer_start",
    "area", "name", "floor",
}

# Per-language rule-name translations. Each language's hassil _common.yaml
# uses local-language rule names (`apaga`, `enciende`, `ausschalten`, …).
# When we promote a rule to a .voc file, we'd rather have a canonical
# English topic name across all languages so the resulting locale tree
# is portable (e.g. all languages' "turn off" vocabulary lives at
# `turn_off.voc`).
#
# Coverage is best-effort — only the high-impact verb concepts are
# mapped here. Languages or rules without an entry fall through to the
# original local-language name. Extend this table as needed.
CANONICAL_RULE_NAMES: dict[str, dict[str, str]] = {
    # Spanish ---------------------------------------------------------
    "es": {
        # actions
        "abre": "open", "cierra": "close",
        "apaga": "turn_off", "enciende": "turn_on",
        "sube": "raise", "baja": "lower",
        "aumenta": "increase", "disminuye": "decrease", "reduce": "decrease",
        "establece": "set", "cambia": "set",
        "establece_abre_cierra": "set_or_adjust",
        "establece_sube_baja": "set_or_adjust",
        "continua": "resume", "continúa": "resume", "vuelve": "resume",
        "resume": "resume",
        "añadir": "add", "anadir": "add", "add": "add",
        "elimina": "remove", "quita": "remove", "resta": "remove",
        "cancela": "cancel", "cancelar_temporizador": "cancel",
        "para": "stop", "pausa": "pause",
        "reproduce": "play", "inicia": "start",
        "salta": "skip", "ejecuta": "run", "crea": "create",
        "mide": "measure", "dime": "tell_me",
        # concepts
        "anterior": "previous", "ahora": "now",
        "casa": "home", "aqui": "here", "de_aqui": "from_here",
        "todos": "all", "todas_partes": "everywhere",
        "temp": "temp", "porciento": "percent",
        "temporizador": "timer", "temporizadores": "timers",
        "cerrables": "closable", "luces": "lights", "puerta": "door",
        "pista": "track", "vol": "volume", "habitacion": "room",
        "se_encuentra": "where_is", "cual_es": "what_is",
        "cuantos": "how_many", "otra_vez": "again",
        # local-only (Spanish-specific contraction)
        "en_el": "in_the",
    },
    # Catalan ---------------------------------------------------------
    "ca": {
        # actions
        "obre": "open", "tanca": "close",
        "engega": "turn_on", "apaga": "turn_off",
        "engega_stt_typo": "turn_on", "apaga_stt_typo": "turn_off",
        "al_stt_typo": "turn_on", "llums_typo": "lights",
        "puja": "raise", "pujar": "raise", "baixar": "lower",
        "afegir": "add", "elimina": "remove",
        "cancelar": "cancel", "cancela": "cancel",
        "pausar": "pause", "reactiva": "resume",
        "reproduir": "play", "reproduir_again": "play",
        "torna_a": "play_again", "configura": "set",
        # concepts
        "actual": "now", "anterior": "previous",
        "again": "again", "hora": "time",
        "temporitzador": "timer", "bateria": "battery",
        "tot": "all", "element": "item", "volum": "volume",
        "llums": "lights", "esta_hiha": "is_there",
        "quin_es": "what_is", "how_much": "how_much",
        "can_you": "can_you",
        "seguent": "next", "percent": "percent",
        # local-only (Catalan grammar markers)
        "nombre_indeterminat": "nombre_indeterminat",
        "objectes_amb_clau": "objectes_amb_clau",
        "preposicio": "preposicio", "preposicio_base": "preposicio_base",
        "preposicio_base_singular": "preposicio_base_singular",
        "preposicio_base_plural": "preposicio_base_plural",
        "preposicio_singular": "preposicio_singular",
        "preposicio_singular_masc": "preposicio_singular_masc",
        "pronom": "pronom", "pronom_singular": "pronom_singular",
        "pronom_plural": "pronom_plural",
    },
    # French ----------------------------------------------------------
    "fr": {
        # actions
        "ouvre": "open", "ferme": "close",
        "allume": "turn_on", "éteins": "turn_off", "eteins": "turn_off",
        "eteins_dirty": "turn_off", "mets_dirty": "turn_on",
        "augmente": "increase", "diminue": "decrease",
        "monte": "raise", "baisse": "lower", "descend": "lower",
        "ajoute": "add", "supprime": "remove", "enleve": "remove",
        "annonce": "broadcast", "arrete": "stop", "active": "start",
        "demarre": "start", "cree": "create", "nettoie": "clean",
        "regle": "set", "mets": "set", "reprends": "resume",
        "verrouille": "lock", "deverrouille": "unlock",
        "lecture": "play", "lis": "play",
        "tond": "mow", "eclaire": "light_up",
        "renvoie": "return", "donnemoi": "give_me",
        # concepts
        "pourcent": "percent", "degres": "degrees",
        "aujourdhui": "today", "completement": "completely",
        "tous": "all", "partout": "everywhere", "ici": "here",
        "lumiere": "light", "appareil": "device", "capteur": "sensor",
        "fenetre": "window", "serrure": "lock_device",
        "maison": "home", "pelouse": "lawn", "media": "media",
        "piece": "room", "volume": "volume",
        "ventilateur": "fan", "ventilateurs": "fans",
        "minuteur": "timer", "minuteurs": "timers",
        "estil": "is_it", "atil": "is_there", "yatil": "is_there_any",
        "ou_je_suis": "where_am_i", "quel": "which", "quelest": "what_is",
        "en_route": "en_route", "hour_unit": "hour_unit",
        "minute_unit": "minute_unit", "second_unit": "second_unit",
        "m_unit": "meter_unit", "s_unit": "second_unit",
        # local-only (French grammar)
        "le": "le", "au": "au", "mon": "mon",
        "dans": "dans", "de": "de",
    },
    # German ----------------------------------------------------------
    "de": {
        # actions
        "einschalten": "turn_on", "ausschalten": "turn_off",
        "schalten": "switch_action", "machen": "do",
        "öffnen": "open", "schließen": "close",
        "schliessen": "close", "schliessen_end_of_sentence": "close",
        "offnen_end_of_sentence": "open", "absperren": "lock",
        "erhöhen": "increase", "verringern": "decrease",
        "starten": "start", "starte": "start",
        "starten_end_of_sentence": "start",
        "stoppen": "stop", "stelle": "set",
        "setze": "set", "setzen": "set", "setzen_end_of_sentence": "set",
        "aktivieren": "activate", "ausfuehren": "run",
        "entsperren": "unlock", "sperren": "lock",
        "fahren": "drive", "wiederhole": "repeat",
        "erstelle": "create", "leuchten_lassen": "turn_on",
        "media_mute": "mute", "media_unmute": "unmute",
        # concepts
        "batterie": "battery", "ladestand": "battery_level",
        "alle": "all", "hier": "here", "welche": "which",
        "irgend": "any", "etwas": "any", "ding": "thing",
        "fenster": "window", "tuer": "door", "tor": "gate",
        "garage": "garage", "abdeckung": "cover",
        "licht": "light", "lichter": "lights", "lichtes": "lights",
        "lichtes_mit_artikel": "lights", "licht_ohne_artikel": "light",
        "luefter": "fan", "rollladen": "shutter",
        "co": "co", "co_sensor": "co_sensor",
        "gas_sensor": "gas_sensor", "source_of_noise": "noise_source",
        "im_zuhause": "at_home", "ist_wurde": "is_was",
        "sind_wurden": "are_were", "wieviel": "how_much",
        "naechster": "next", "vorheriger_letzter": "previous",
        "skript": "script", "szene": "scene", "song": "song",
        "media_type": "media_type", "erkannt": "detected",
        "schloss": "lock_device", "timer_decrease": "timer_decrease",
        "timer_cancel_end_of_sentence": "timer_cancel",
        "timer_set_end_of_sentence": "timer_set",
        "timer_decrease_end_of_sentence": "timer_decrease",
        # German grouping aliases — all variants fold to one canonical
        "alle_abdeckungen": "all_covers", "alle_garagen": "all_garages",
        "alle_lichter": "all_lights",
        "alle_lichter_ueberall": "all_lights_everywhere",
        "alle_luefter": "all_fans",
        "luefter_genitiv": "fan", "luefter_ueberall": "all_fans",
        # local-only (German grammar)
        "an": "an", "aus": "aus", "auf": "auf", "zu": "zu",
        "artikel": "artikel", "artikel_bestimmt": "artikel_bestimmt",
        "artikel_unbestimmt": "artikel_unbestimmt",
        "alle_genitiv": "alle_genitiv",
        "possessivpronom_mein": "possessivpronom_mein",
        "possessivpronom_unser": "possessivpronom_unser",
        "preposition": "preposition",
        "from_the": "from_the", "to_the": "to_the",
    },
    # Portuguese (BR) -------------------------------------------------
    "pt-BR": {
        "abrir": "open", "fechar": "close",
        "ligar": "turn_on", "desligar": "turn_off",
        "aumentar": "increase", "diminuir": "decrease",
        "adicionar": "add", "remover": "remove",
        "retirar": "remove", "deletar": "remove",
        "cancelar": "cancel", "pausar": "pause",
        "iniciar": "start", "terminar": "stop", "completar": "complete",
        "colocar": "put", "juntar": "add", "mudar": "set",
        "tornar": "set", "retornar": "resume",
        "alarme": "timer", "brilho": "brightness",
        "cade": "where_is", "algum": "some", "qual": "which",
        "casa": "home", "ventilador": "fan",
        "temporizador": "timer", "temporizadores": "timers",
        "esta": "is_at", "falta": "remaining",
        "cortina": "curtain", "todas": "all",
        "por": "by",
        # local-only
        "artigos": "artigos",
    },
    # Portuguese (PT) -------------------------------------------------
    "pt-PT": {
        "abrir": "open", "fechar": "close",
        "ligar": "turn_on", "desligar": "turn_off",
        "aumentar": "increase", "diminuir": "decrease",
        "adicionar": "add", "remover": "remove",
        "cancelar": "cancel", "pausar": "pause",
    },
    # Italian ---------------------------------------------------------
    "it": {
        "apri": "open", "chiudi": "close",
        "accendi": "turn_on", "spegni": "turn_off",
        "aumenta": "increase", "diminuisci": "decrease",
        "alza": "raise", "abbassa": "lower",
        "metti": "put", "fai": "do", "annuncia": "broadcast",
        "fermati": "stop", "avvia": "start",
        "announce": "broadcast", "put": "put", "made": "made",
        "triggered": "triggered", "to_do": "to_do",
        "to_lock": "to_lock", "hello": "hello",
        "home": "home", "climate": "climate",
        "cover": "cover", "fan": "fan", "garage": "garage",
        "light": "light", "lock": "lock_device",
        "locked": "locked", "unlocked": "unlocked",
        "opened": "opened", "closed": "closed",
        "there_is": "there_is", "hour_unit": "hour_unit",
        "minute_unit": "minute_unit", "second_unit": "second_unit",
        "in_here": "here",
        # local-only (Italian articles/prepositions)
        "the": "the", "at": "at", "in": "in", "of": "of",
        "to": "to", "from": "from", "onto": "onto", "on": "on",
        "some": "some", "my": "my",
    },
    # Dutch -----------------------------------------------------------
    "nl": {
        "open": "open", "sluit": "close",
        "open_action": "open", "close_action": "close",
        "open_command": "open", "close_command": "close",
        "close_command_suffix": "close",
        "schakel_in": "turn_on", "schakel_uit": "turn_off",
        "verhoog": "increase", "verlaag": "decrease",
        "change": "set", "change_infinitive": "set",
        "detect": "detect", "by": "by", "here": "here",
        "brightness": "brightness",
        "brightness_no_article": "brightness",
        "light": "light", "light_no_article": "light",
        "light_composed": "light", "room_light": "light",
        "all_light": "all_lights",
        "cover": "cover", "curtain": "curtain", "blind": "blind",
        "awning": "awning", "shade": "shade", "shutter": "shutter",
        "door": "door", "gate": "gate", "garage": "garage",
        "window": "window", "fan": "fan",
        "lock": "lock_device", "locked": "locked", "unlocked": "unlocked",
        "closed": "closed",
        "switch": "switch", "sensor": "sensor",
        "media_item": "media_item", "timer": "timer",
        "timer_named": "timer_named", "to": "to",
        "warm": "warm", "what_is": "what_is",
        "state": "state", "degrees": "degrees",
        # local-only
        "in": "in", "is": "is", "my": "my",
        "numeric_value_set": "numeric_value_set",
    },
    # Romanian --------------------------------------------------------
    "ro": {
        "deschide": "open", "inchide": "close",
        "porneste": "turn_on", "opreste": "turn_off",
        "porneste_timer": "timer_set", "opreste_timer": "timer_cancel",
        "reia_timer": "timer_resume", "suspenda_timer": "timer_pause",
        "modifica_temperatura": "set_temperature",
        "adauga": "add", "sterge": "remove",
        "seteaza": "set", "ruleaza": "run", "reda": "play",
        "aspira": "vacuum",
        "adauga_amount_la_complement": "add_amount",
        "scade_amount_din_complement": "subtract_amount",
        "precedentul": "previous", "urmatorul": "next",
        "numit": "named", "exista": "exists", "este": "is",
        "detectat": "detected", "nedetectat": "not_detected",
        "detectate": "detected", "nedetectate": "not_detected",
        "cald": "warm", "frig": "cold", "cald_frig": "warm_cold",
        "lumina": "light", "luminile": "lights",
        "luminozitatea": "brightness",
        "dispozitiv": "device", "dispozitive": "devices",
        "fereastra": "window", "ferestrele": "windows",
        "poarta": "gate", "portile": "gates",
        "ventilatorul": "fan", "ventilatoarele": "fans",
        "ventilatorului": "fan", "ventilatoarelor": "fans",
        "usa": "door", "usile": "doors",
        "intrerupatorul": "switch", "intrerupatoarele": "switches",
        "incuietoarea": "lock_device", "incuietorile": "locks",
        "incuiat": "locked", "incuiate": "locked", "descuiat": "unlocked",
        "descuiate": "unlocked",
        "deschis": "opened", "deschise": "opened",
        "inchis": "closed", "inchise": "closed",
        "pornit": "on", "pornite": "on", "oprit": "off", "oprite": "off",
        "ore": "hours", "minute": "minutes", "secunde": "seconds",
        "temporizatorul": "timer", "temporizatorului": "timer",
        "toti": "all", "jumatate": "half",
        "temperatura": "temperature", "temperatura_aerului": "air_temperature",
        "de_aici": "from_here", "vreun": "any", "temporar": "temporary",
        "pozitia": "position", "viteza": "speed", "volumul": "volume",
        "la_suta": "percent", "maximum": "max", "minimum": "min",
        "culoarea": "color", "care": "which",
        "cat": "how_many", "cate": "how_many", "cat_quant": "how_much",
        "pana_la": "until", "cu": "with",
        # local-only
        "de": "de", "in": "in", "din": "din", "la": "la",
    },
    # Finnish ---------------------------------------------------------
    "fi": {
        "avaa": "open", "sulje": "close",
        "kytke": "turn_on", "paalta": "turn_off",
        "kaynnista": "start", "pysayta": "stop",
        "kerro": "tell",
        "kytkimet": "switches", "kytkin": "switch",
        "laita": "put", "laite": "device",
        "valo": "light", "valot": "lights",
        "valaistus": "lighting", "valaistukset": "lights",
        "kirkkaus": "brightness",
        "kirkkaudeksi": "brightness", "kirkkaudelle": "brightness",
        "kirkkauteen": "brightness",
        "vari": "color",
        "varit": "colors", "variin": "color", "vareihin": "colors",
        "variksi": "color", "vareiksi": "colors",
        "varille": "color", "vareille": "colors", "variltaan": "color",
        "lampotila": "temperature",
        "nyt": "now", "paikka": "place",
        "kuinka": "how", "paljonko": "how_much", "montako": "how_many",
        "kuuma": "hot", "kuumaa": "hot", "kuumaksi": "hot",
        "kuuman": "hot", "kuumana": "hot",
        "kylma": "cold", "kylmaa": "cold", "kylmaksi": "cold",
        "kylman": "cold", "kylmana": "cold",
        "jokin": "any", "jotkut": "some", "kaikki": "all",
        "onko": "is_it", "ovatko": "are_they",
        "tuuletin": "fan", "tuulettimet": "fans",
        # local-only (Finnish case morphology)
        "alue": "alue", "alueella": "alueella", "alueelle": "alueelle",
        "alueelta": "alueelta", "alueen": "alueen",
        "alueeseen": "alueeseen", "alueessa": "alueessa",
        "alueesta": "alueesta", "alue_taivutus": "alue_taivutus",
        "kirkkaus_taivutus": "kirkkaus_taivutus",
        "laite_taivutus": "laite_taivutus", "vari_taivutus": "vari_taivutus",
        "laitteelle": "laitteelle", "laitteelta": "laitteelta",
        "laitteen": "laitteen", "laitteeseen": "laitteeseen",
        "laitteessa": "laitteessa", "laitteesta": "laitteesta",
    },
    # Galician --------------------------------------------------------
    "gl": {
        "abre": "open", "pecha": "close",
        "acende": "turn_on", "apaga": "turn_off",
        "baixa": "lower", "sube": "raise",
        "fecha_con_chave": "lock",
        "cancela": "cancel", "salta": "skip",
        "para": "stop", "pausa": "pause",
        "engadir": "add", "elimina": "remove",
        "poner": "put", "establece": "set",
        "continua": "resume", "volve": "resume",
        "reproduce": "play", "inicia": "start",
        "anterior": "previous", "seguinte": "next",
        "algun": "some", "todos": "all", "todas_partes": "everywhere",
        "de_aqui": "from_here", "esta": "is",
        "cal": "which", "cal_e": "what_is", "que_marca": "showing",
        "porcento": "percent",
        "temporizador": "timer", "temporizadores": "timers",
        "crea": "create", "dime": "tell_me",
        "luces": "lights", "casa": "home", "habitacion": "room",
        "pista": "track", "abre_quitafeche": "set_or_adjust",
        "outra_vez": "again", "pechables": "closable",
        "establece_abre_pecha": "set_or_adjust",
        "establece_sube_baixa": "set_or_adjust",
        # local-only
        "meu": "meu", "con": "con", "en": "en", "por": "por",
    },
    # Slovak ----------------------------------------------------------
    "sk": {
        # already mostly English in source
        "previous_acc": "previous", "previous_nom": "previous",
        "turn_on_activate": "turn_on", "turn_off_light": "turn_off",
        "turn_on_light": "turn_on",
    },
    # Hungarian -------------------------------------------------------
    "hu": {
        "zar": "lock",
        "futtat": "run", "foglalt": "busy",
        "helyen": "at_place", "jelenlet": "presence",
        "melyik": "which", "mennyi": "how_much",
        "minden": "all", "mindenhol": "everywhere",
        "nincs_otthon": "not_at_home", "otthon": "home",
        "szemely": "person", "szenzor": "sensor",
        "szinhomerseklet": "color_temperature",
        "valaki": "somebody", "vane": "is_there",
        "ventilator": "fan", "eszkoz": "device",
        "fenyero": "brightness", "barmelyik": "any",
        "open_close_dev": "set_or_adjust",
        "open_dev": "open", "close_dev": "close",
        # local-only (Hungarian morphology)
        "area_ragok": "area_ragok", "area_szavak": "area_szavak",
        "name_ragok": "name_ragok", "name_szavak": "name_szavak",
        "ragok": "ragok",
        "idojarashelyek": "idojarashelyek", "idojarasragok": "idojarasragok",
    },
    # Norwegian Bokmål ------------------------------------------------
    "nb": {
        "alle": "all", "apen": "open", "apne": "open",
        "aktiver": "activate", "bryter": "switch",
        "endre": "set", "garasje": "garage",
        "gardin": "curtain", "gjenstar": "remaining",
        "hvilke": "which",
        "kald": "cold", "kaldt_varmt": "cold_warm",
        "las": "lock", "lukk": "close", "lukket": "closed",
        "lys": "light", "maleenhet": "measurement_unit",
        "malt": "measured", "markise": "awning",
        "noe": "any",
        "persienne": "shutter", "port": "gate",
        "programvare": "software",
        "rullegardin": "roller_blind", "rykvarsler": "smoke_alarm",
        "skodde": "shutter_cover",
        "skru_av": "turn_off", "skru_pa": "turn_on",
        "tilstand": "state", "varm": "warm",
        "vifte": "fan", "vindu": "window", "dr": "door",
        "i_pa": "in_on",
    },
    # Czech -----------------------------------------------------------
    "cs": {
        "aktivovat": "activate", "bude": "will_be", "byl": "was",
        "casovac": "timer", "dalsi": "next",
        "hodina": "hour", "jaky_je": "what_is", "je": "is",
        "koncentrace": "concentration", "ktere": "which",
        "minuta": "minute", "nastavit": "set",
        "nektere": "some", "obecne_zmenit": "set",
        "odemknout": "unlock", "otevrit": "open",
        "oznam": "announce", "pojmenovany": "named",
        "predchozi": "previous", "prejit": "skip",
        "rozsvitit": "turn_on", "roztahnout": "open",
        "sekunda": "second", "spustit": "start",
        "svetla": "lights", "tady": "here",
        "upravit": "set", "vsude": "everywhere",
        "vypnout": "turn_off", "zamknout": "lock",
        "zapnout": "turn_on", "zatahnout": "close",
        "zavrit": "close", "zhasnout": "turn_off",
        "zmenit": "set", "ztlumit": "dim",
        "zvysit": "increase",
        # local-only
        "v": "v", "y_e": "y_e",
    },
    # Chinese (Simplified) --------------------------------------------
    "zh-CN": {
        "add_to": "add", "set_to": "set",
        "how_many_is": "how_many", "how_much": "how_much",
    },
    # Chinese (Hong Kong) ---------------------------------------------
    "zh-HK": {
        "set_to": "set", "how_many_is": "how_many",
        "how": "how",
    },
    # Chinese (Traditional) -------------------------------------------
    "zh-TW": {
        "set_to": "set", "how_many_is": "how_many",
    },
    # Swedish ---------------------------------------------------------
    "sv": {
        "alla": "all", "andra": "set",
        "ar": "is", "batteri": "battery",
        "dimra": "dim", "farga": "color",
        "gardiner": "curtains",
        "hemma": "home", "inga": "none", "i_pa": "in_on",
        "kall": "cold", "lasbar": "lockable",
        "ljusintensitet": "brightness",
        "ljuskallor": "light_sources",
        "maximal": "max", "minimal": "min",
        "mojliga": "possible",
        "oppna_gardiner": "open_curtains",
        "procent": "percent",
        "satt_numeriskt_varde": "numeric_value_set",
        "sla_av": "turn_off", "sla_pa": "turn_on",
        "stang_gardiner": "close_curtains",
        "time_left": "time_left",
        "vad": "what", "var": "where", "varm": "warm",
        "varmt_kallt": "warm_cold", "vilka": "which",
    },
    # Slovenian -------------------------------------------------------
    "sl": {
        "dodaj": "add",
        "izkljuci": "turn_off", "izklopi": "turn_off",
        "ugasni": "turn_off",
        "vkljuci": "turn_on", "vklopi": "turn_on",
        "prizgi": "turn_on",
        "odpri": "open", "zapri": "close",
        "kaksna_je": "what_is", "kaksno_je": "what_is",
        "katera": "which", "katera_je": "which",
        "kateri": "which", "kje_je": "where_is",
        "luc": "light",
        "pol": "half", "povsod": "everywhere",
        "so_vsi": "are_all", "spremeni": "set",
        "stopinj": "degrees", "ventilator": "fan",
        "vsa": "all", "vse": "all", "vsi": "all",
        # local-only
        "v": "v",
    },
    # Welsh -----------------------------------------------------------
    "cy": {
        "agor": "open", "cau": "close",
        "cynnau": "turn_on", "diffodd": "turn_off",
        "amser_canslo": "timer_cancel", "amser_gosod": "timer_set",
        "ar_hyn_o_bryd": "currently",
        "beth_yw": "what_is", "ble_mae": "where_is",
        "cartref": "home", "cyflwr": "state",
        "faint": "how_many", "glanhau": "clean",
        "golau": "light", "gosod": "set",
        "gosod_rhif": "numeric_value_set",
        "oes": "is", "oes_unrhyw": "is_any",
        "pa": "which", "pob": "all",
        "rhoi": "set", "sut_mae": "how_is",
        "troi": "turn", "tymheredd_gair": "temperature_word",
        "unrhyw": "any", "yma": "here",
        "ym_mhobman": "everywhere", "ydy_pob": "is_all",
        # local-only
        "ar": "ar", "ein": "ein", "fy": "fy",
        "i": "i", "o": "o", "y": "y", "yn": "yn",
    },
    # Polish ----------------------------------------------------------
    "pl": {
        "turn_on_light": "turn_on",
    },
    # Vietnamese ------------------------------------------------------
    "vi": {
        "mo": "open", "bao_nhieu": "how_many",
        "every_where": "everywhere", "in_here": "here",
        "showed_by": "shown_by",
        # local-only
        "ong": "ong", "of": "of", "in": "in",
    },
    # Thai ------------------------------------------------------------
    "th": {
        "be": "is", "is_it": "is_it",
        "lead_in": "lead_in", "now": "now",
        "second_person": "you",
        "temperature_unit": "temperature_unit",
        "timer_status_query": "timer_status", "timer_word": "timer",
        # local-only Thai politeness markers
        "polite_prefix": "polite_prefix",
        "polite_prefix_base": "polite_prefix_base",
        "polite_suffix": "polite_suffix",
        "polite_suffix_core": "polite_suffix_core",
        "polite_suffix_ending": "polite_suffix_ending",
    },
    # Croatian / Serbian-Latin (very similar) -------------------------
    "hr": {
        "iskljuci": "turn_off", "ukljuci": "turn_on",
        "otvori": "open", "zatvori": "close",
        "kakvo_je": "what_is", "koja_je": "which",
        "sve": "all", "promijeni": "set",
        "stupanj": "degree", "prognoza": "forecast",
    },
    "sr-Latn": {
        "iskljuci": "turn_off", "ukljuci": "turn_on",
        "otvori": "open", "zatvori": "close",
        "kakvo_je": "what_is", "koja_je": "which",
        "sve": "all", "promeni": "set",
        "stepen": "degree", "prognoza": "forecast",
    },
    # Portuguese (generic — also covers `pt`) -------------------------
    "pt": {
        "abrir": "open", "fechar": "close",
        "ligar": "turn_on", "desligar": "turn_off",
        "adicionar": "add", "colocar": "put",
        "juntar": "add", "mudar": "set",
        "esta": "is", "estores": "blinds",
        "algum": "some", "qual": "which", "luz": "light",
        "temporizador": "timer", "temporizadores": "timers",
        "temporizador_cancelar": "timer_cancel",
        # local-only
        "por": "por",
    },
    # Luxembourgish ---------------------------------------------------
    "lb": {
        "maach": "do", "op": "on", "zou": "off",
        "all_window": "all_windows",
    },
    # Swiss German ----------------------------------------------------
    "de-CH": {
        "ab_us": "turn_off", "a_y": "turn_on",
        "gerate": "device", "liecht": "light",
        "liechter": "lights", "mach": "do", "steu": "control",
    },
    # Arabic — slugs already English-shaped, just a few stragglers ----
    "ar": {
        "procent": "percent", "go": "go", "go_back": "go_back",
        "remains": "remaining", "this": "this",
        "home_assistant": "home_assistant",
    },
    # Danish ----------------------------------------------------------
    "da": {
        # actions
        "tnd": "turn_on", "sluk": "turn_off",
        "luk": "close", "abn": "open",
        "dkke_abn": "open_cover", "dkke_luk": "close_cover",
        "dkke_ned": "lower_cover", "dkke_op": "raise_cover",
        "afspil": "play", "afspiller": "play",
        "spring": "skip", "spring_til": "skip_to",
        "broadcast": "broadcast", "start": "start", "stop": "stop",
        "rengr": "clean", "skabte": "create",
        "fuldfr": "complete", "fuldfrt": "completed",
        "genoptag": "resume", "opfanger": "detect",
        "med_navnet": "named", "pa_alle_lys": "on_all_lights",
        "kommandoer": "commands", "altid": "always",
        # concepts
        "nu": "now", "her": "here", "totalt": "all",
        "forrige": "previous", "nogen": "any",
        "er_nogen": "is_any", "er_noget": "is_anything",
        "hvilke": "which", "hvor_mange": "how_many",
        "den": "the_one", "denne": "this",
        "aktuel_tid": "current_time", "aktuelle": "current",
        "dags_dato": "today_date", "dato": "date",
        "alle_destinationer": "all_destinations",
        "lys": "light", "lydstyrke": "volume",
        "farve": "color", "koldt": "cold",
        "koldt_varmt": "cold_warm", "temperaturen": "temperature",
        "carbonmonoxid": "carbon_monoxide",
        "carbonmonoxid_sensor": "carbon_monoxide_sensor",
        "gas_fundet": "gas_detected",
        "gas_ikke_fundet": "gas_not_detected",
        "bevaegelses_sensor": "motion_sensor",
        "blser": "blinds", "garagedr": "garage_door",
        "gardin": "curtain", "indkbsliste": "shopping_list",
        "lasbar": "lockable", "nedbr": "rainfall",
        "persienne": "shutter", "rullegardin": "roller_blind",
        "skodde": "shutter_cover", "sang": "song",
        "script": "script", "status": "state",
        "medie": "media", "enhed": "device",
        "koncentration": "concentration", "procent": "percent",
        "st_numerisk_vrdi": "numeric_value_set",
        "sprg_om_destination": "ask_for_destination",
        "sprg_om_vrdi": "ask_for_value",
        "i_pa": "in_on", "i": "in",
        "timer_add": "timer_add", "timer_decrease": "timer_decrease",
        "timer_pause": "timer_pause", "timer_unpause": "timer_unpause",
        "timer": "timer", "timers": "timers",
        "hilsen": "greeting", "mine_data": "my_data",
        "abn": "open", "al": "all",
    },
}

# ---------------------------------------------------------------------------
# Common area names — seeded per language so the `{area}` slot gets a
# head-start even though hassil treats area as a wildcard.  This is a
# best-effort list; contributors can extend it for missing languages.
# ---------------------------------------------------------------------------

COMMON_AREA_NAMES: dict[str, list[str]] = {
    "en": ["kitchen", "living room", "bedroom", "bathroom", "office", "garage", "hallway", "basement", "dining room", "garden", "terrace", "laundry room"],
    "de": ["Küche", "Wohnzimmer", "Schlafzimmer", "Badezimmer", "Büro", "Garage", "Flur", "Keller", "Esszimmer", "Garten", "Terrasse", "Waschküche"],
    "fr": ["cuisine", "salon", "chambre", "salle de bain", "bureau", "garage", "couloir", "sous-sol", "salle à manger", "jardin", "terrasse", "buanderie"],
    "es": ["cocina", "salón", "dormitorio", "baño", "oficina", "garaje", "pasillo", "sótano", "comedor", "jardín", "terraza", "lavandería"],
    "pt": ["cozinha", "sala de estar", "quarto", "casa de banho", "escritório", "garagem", "corredor", "cave", "sala de jantar", "jardim", "terraço", "lavandaria"],
    "pt-BR": ["cozinha", "sala", "quarto", "banheiro", "escritório", "garagem", "corredor", "porão", "sala de jantar", "jardim", "terraço", "lavanderia"],
    "it": ["cucina", "soggiorno", "camera da letto", "bagno", "ufficio", "garage", "corridoio", "seminterrato", "sala da pranzo", "giardino", "terrazza", "lavanderia"],
    "nl": ["keuken", "woonkamer", "slaapkamer", "badkamer", "kantoor", "garage", "gang", "kelder", "eetkamer", "tuin", "terras", "wasruimte"],
    "ca": ["cuina", "sala d'estar", "dormitori", "bany", "oficina", "garatge", "passadís", "soterrani", "sala de dinar", "jardí", "terrassa", "sala de bugada"],
    "da": ["køkken", "stue", "soveværelse", "badeværelse", "kontor", "garage", "gang", "kælder", "spisestue", "have", "terrasse", "vaskerum"],
    "sv": ["kök", "vardagsrum", "sovrum", "badrum", "kontor", "garage", "hall", "källare", "matsal", "trädgård", "terrass", "tvättstuga"],
    "nb": ["kjøkken", "stue", "soverom", "bad", "kontor", "garasje", "gang", "kjeller", "spisestue", "hage", "terrasse", "vaskerom"],
    "fi": ["keittiö", "olohuone", "makuuhuone", "kylpyhuone", "toimisto", "autotalli", "käytävä", "kellari", "ruokailuhuone", "puutarha", "terassi", "pesula"],
    "pl": ["kuchnia", "salon", "sypialnia", "łazienka", "biuro", "garaż", "korytarz", "piwnica", "jadalnia", "ogród", "taras", "pralnia"],
    "ru": ["кухня", "гостиная", "спальня", "ванная", "офис", "гараж", "коридор", "подвал", "столовая", "сад", "терраса", "прачечная"],
    "ro": ["bucătărie", "sufragerie", "dormitor", "baie", "birou", "garaj", "hol", "subsol", "sală de mese", "grădină", "terasă", "spălătorie"],
    "ar": ["مطبخ", "غرفة المعيشة", "غرفة النوم", "حمام", "مكتب", "مرآب", "ممر", "قبو", "غرفة الطعام", "حديقة", "شرفة", "غرفة الغسيل"],
    "he": ["מטבח", "סלון", "חדר שינה", "אמבטיה", "משרד", "מוסך", "מסדרון", "מרתף", "חדר אוכל", "גן", "מרפסת", "חדר כביסה"],
    "ja": ["キッチン", "リビング", "寝室", "浴室", "書斎", "ガレージ", "廊下", "地下室", "ダイニング", "庭", "テラス", "洗濯室"],
    "ko": ["부엌", "거실", "침실", "욕실", "사무실", "차고", "복도", "지하실", "식당", "정원", "테라스", "세탁실"],
    "zh-CN": ["厨房", "客厅", "卧室", "浴室", "办公室", "车库", "走廊", "地下室", "餐厅", "花园", "露台", "洗衣房"],
    "zh-TW": ["廚房", "客廳", "臥室", "浴室", "辦公室", "車庫", "走廊", "地下室", "餐廳", "花園", "露台", "洗衣房"],
    "zh-HK": ["廚房", "客廳", "臥室", "浴室", "辦公室", "車庫", "走廊", "地下室", "餐廳", "花園", "露台", "洗衣房"],
    "el": ["κουζίνα", "σαλόνι", "υπνοδωμάτιο", "μπάνιο", "γραφείο", "γκαράζ", "διάδρομος", "υπόγειο", "τραπεζαρία", "κήπος", "βεράντα", "πλυντήριο"],
    "hu": ["konyha", "nappali", "hálószoba", "fürdőszoba", "iroda", "garázs", "folyosó", "pince", "étkező", "kert", "terasz", "mosókonyha"],
    "cs": ["kuchyně", "obývací pokoj", "ložnice", "koupelna", "kancelář", "garáž", "chodba", "sklep", "jídelna", "zahrada", "terasa", "prádelna"],
    "sk": ["kuchyňa", "obývačka", "spálňa", "kúpeľňa", "kancelária", "garáž", "chodba", "pivnica", "jedáleň", "záhrada", "terasa", "práčovňa"],
    "sl": ["kuhinja", "dnevna soba", "spalnica", "kopalnica", "pisarna", "garaža", "hodnik", "klet", "jedilnica", "vrt", "terasa", "pralnica"],
    "hr": ["kuhinja", "dnevni boravak", "spavaća soba", "kupaonica", "ured", "garaža", "hodnik", "podrum", "blagovaonica", "vrt", "terasa", "praona"],
    "sr": ["кухиња", "дневна соба", "спаваћа соба", "купатило", "канцеларија", "гаража", "ходник", "подрум", "трпезарија", "башта", "тераса", "пераоница"],
    "sr-Latn": ["kuhinja", "dnevna soba", "spavaća soba", "kupatilo", "kancelarija", "garaža", "hodnik", "podrum", "trpezarija", "bašta", "terasa", "peraonica"],
    "bg": ["кухня", "хол", "спалня", "баня", "офис", "гараж", "коридор", "мазе", "трапезария", "градина", "тераса", "пералня"],
    "uk": ["кухня", "вітальня", "спальня", "ванна кімната", "офіс", "гараж", "коридор", "підвал", "їдальня", "сад", "тераса", "пральня"],
    "tr": ["mutfak", "oturma odası", "yatak odası", "banyo", "ofis", "garaj", "koridor", "bodrum", "yemek odası", "bahçe", "teras", "çamaşır odası"],
    "th": ["ครัว", "ห้องนั่งเล่น", "ห้องนอน", "ห้องน้ำ", "ห้องทำงาน", "โรงรถ", "ทางเดิน", "ใต้ดิน", "ห้องอาหาร", "สวน", "ระเบียง", "ห้องซักรีด"],
    "vi": ["nhà bếp", "phòng khách", "phòng ngủ", "phòng tắm", "văn phòng", "ga-ra", "hành lang", "tầng hầm", "phòng ăn", "vườn", "hiên", "phòng giặt"],
    "id": ["dapur", "ruang tamu", "kamar tidur", "kamar mandi", "kantor", "garasi", "koridor", "ruang bawah tanah", "ruang makan", "taman", "teras", "ruang cuci"],
    "ms": ["dapur", "ruang tamu", "bilik tidur", "bilik air", "pejabat", "garaj", "koridor", "ruang bawah tanah", "ruang makan", "taman", "teres", "bilik dobi"],
    "ga": ["cistin", "seomra suí", "seomra codlata", "seomra folctha", "oifig", "garáiste", "halla", "bunús", "seomra bia", "gairdín", "terrás", "seomra níocháin"],
    "cy": ["gegin", "ystafell fyw", "ystafell wely", "ystafell ymolchi", "swyddfa", "garej", "coridor", "celar", "ystafell fwyta", "gardd", "teras", "ystafell golchi"],
    "et": ["köök", "elutuba", "magamistuba", "vannituba", "kontor", "garaaž", "koridor", "kelder", "söögituba", "aed", "terass", "pesuruum"],
    "lt": ["virtuvė", "svetainė", "miegamasis", "vonios kambarys", "biuras", "garažas", "koridorius", "rūsys", "valgomasis", "sodas", "terasa", "skalbykla"],
    "lv": ["virtuve", "dzīvojamā istaba", "guļamistaba", "vannas istaba", "birojs", "garāža", "koridors", "pagrabs", "ēdamistaba", "dārzs", "terase", "veļas mazgātava"],
    "is": ["eldhús", "stofa", "svefnherbergi", "baðherbergi", "skrifstofa", "bílskúr", "gangur", "kjallari", "borðstofa", "garður", "svalir", "þvottahús"],
    "af": ["kombuis", "sitkamer", "slaapkamer", "badkamer", "kantoor", "motorhuis", "gang", "kelder", "eetkamer", "tuin", "terras", "wasgoedkamer"],
    "sw": ["jiko", "sebule", "chumba cha kulala", "bafu", "ofisi", "jengo la magari", "njia", "chumba cha chini", "chumba cha kula", "bustani", "varanda", "chumba cha kufulia"],
    "eu": ["sukaldea", "egongela", "logela", "bainugela", "bulegoa", "garajea", "korridorea", "sotoa", "janogela", "lorategia", "terraza", "garbitze-gela"],
    "gl": ["cociña", "sala de estar", "dormitorio", "cuarto de baño", "oficina", "garaxe", "corredor", "sótano", "comedor", "xardín", "terraza", "lavandería"],
    "fa": ["آشپزخانه", "اتاق نشیمن", "اتاق خواب", "حمام", "دفتر", "گاراژ", "راهرو", "زیرزمین", "اتاق غذاخوری", "باغ", "تراس", "اتاق لباسشویی"],
    "ne": ["भान्सा", "बैठक कोठा", "सुत्ने कोठा", "बाथरूम", "कार्यालय", "ग्यारेज", "बार", "भुइँतला", "भोजन कोठा", "बगैंचा", "चर्पी", "धुन पखाल्ने कोठा"],
    "ka": ["სამზარეულო", "მისაღები ოთახი", "საძინებელი", "აბაზანა", "ოფისი", "ავტოფარეხი", "კორიდორი", "სარდაფი", "სასადილო ოთახი", "ფანჯარა", "ტერასა", "საპარსი"],
    "bn": ["রান্নাঘর", "বসার ঘর", "শোনার ঘর", "বাথরুম", "অফিস", "গ্যারেজ", "বারান্দা", "বেসমেন্ট", "খাবার ঘর", "বাগান", "টেরাস", "ধোপার ঘর"],
    "gu": ["રસોડું", "બેઠક", "સુવાનો ઓરડો", "બાથરૂમ", "ઓફિસ", "ગેરેજ", "બાર", "બેઝમેન્ટ", "જમવાનું ઓરડો", "બગીચો", "ટેરેસ", "ધોવાનો ઓરડો"],
    "hi": ["रसोई", "बैठक", "बेडरूम", "बाथरूम", "दफ़्तर", "गैराज", "गली", "बेसमेंट", "भोजन कक्ष", "बगीचा", "बरामदा", "धोने का कमरा"],
    "kn": ["ಅಡಿಗೆ ಮನೆ", "ಹಾಲ್", "ನಿದ್ರಾಕೋಶ", "ಬಾತ್ರೂಮ್", "ಕಚೇರಿ", "ಗಾರೇಜ್", "ಕಾರಿಡಾರ್", "ಬೇಸ್ಮೆಂಟ್", "ಊಟದ ಕೋಶ", "ತೋಟ", "ಟೆರೇಸ್", "ಒಗ್ಗುವ ಕೋಶ"],
    "ml": ["അടുക്കളം", "കഴിക്കുന്ന മുറി", "കിടക്കയ്ക്കുള്ള മുറി", "കുളിമുറി", "ഓഫീസ്", "ഗാരേജ്", "കോറിഡോർ", "ബേസ്മെന്റ്", "ഭക്ഷണമുറി", "പൂന്തോട്ടം", "ടെറസ്", "വസ്ത്രം കഴിയുന്ന മുറി"],
    "mr": ["स्वयंपाकघर", "बसण्याची खोली", "जोपायची खोली", "बाथरूम", "ऑफिस", "गॅरेज", "कॉरिडॉर", "बेसमेंट", "जेवणाची खोली", "बाग", "टेरेस", "धुण्याची खोली"],
    "pa": ["ਰਸੋਈ", "ਬੈਠਕ", "ਸੌਣ ਵਾਲਾ ਕਮਰਾ", "ਬਾਥਰੂਮ", "ਦਫਤਰ", "ਗੈਰੇਜ", "ਗਲੀ", "ਬੇਸਮੈਂਟ", "ਖਾਣ ਵਾਲਾ ਕਮਰਾ", "ਬਾਗ", "ਟੈਰੇਸ", "ਧੋਣ ਵਾਲਾ ਕਮਰਾ"],
    "ta": ["சமையலறை", "பெற்று அறை", "கடுக்கை அறை", "குளியலறை", "பணி இடம்", "வாகன நிறுத்தம்", "நடைபாதை", "அடித்தளம்", "உணவு அறை", "தோட்டம்", "முற்றம்", "துவைப்பு அறை"],
    "te": ["వంటగది", "సభా గది", "నిద్ర గది", "స్నానగది", "కార్యాలయం", "గ్యారేజ్", "కారిడార్", "బేస్మెంట్", "భోజన గది", "తోట", "టెరస్", "ఉతికే గది"],
    "ur": ["باتھ روم", "بیٹھک", "سونے کا کمرہ", "باتھ روم", "دفتر", "گیراج", "گلی", "تہہ خانہ", "کھانے کا کمرہ", "باغ", "چبوترا", "دھونے کا کمرہ"],
    "mn": ["гал тогоо", "зочны өрөө", "унтлагын өрөө", "усанд орох өрөө", "оффис", "гараж", "коридор", "суурь", "хоолны өрөө", "цэцэрлэг", "терасс", "угаалгын өрөө"],
    "kw": ["kek", "rom godhesi", "kewor", "rom ymolchi", "offis", "garaj", "koryor", "kelder", "rom dybri", "lowarth", "teras", "rom yowghi"],
    "lb": ["Kichen", "Wunnzëmmer", "Schlofzëmmer", "Buedzëmmer", "Büro", "Garage", "Gank", "Keller", "Iesszëmmer", "Gaart", "Terrass", "Wäschkichen"],
}

# ---------------------------------------------------------------------------
# Template rewriting
# ---------------------------------------------------------------------------

_SLOT_RE = re.compile(r"\{([^{}]+)\}")
_RULE_RE = re.compile(r"<([^<>\s]+)>")
_PERM_RE = re.compile(r"\(([^()]*;[^()]*)\)")           # innermost permutation
_JINJA_SET_RE = re.compile(r"\{%\s*set\b.*?%\}", re.DOTALL)
_JINJA_IF_RE = re.compile(r"\{%\s*if\b[^%]*%\}", re.DOTALL)
_JINJA_ENDIF_RE = re.compile(r"\{%\s*endif\s*%\}", re.DOTALL)
_JINJA_BRANCH_RE = re.compile(r"\{%\s*el(?:if|se)\b[^%]*%\}", re.DOTALL)
_JINJA_SLOT_DOT_RE = re.compile(
    r"\{\{\s*(?:slots|state|query)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|[^}]+?)?\s*\}\}"
)
_JINJA_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|[^}]+?)?\s*\}\}")
_JINJA_LEFTOVER_RE = re.compile(r"\{\{|\}\}|\{%|%\}")


def _rewrite_slot(body: str, slot_to_list: dict[str, str]) -> str:
    body = body.strip()
    if body.startswith("@"):
        name = _slug(body[1:].strip())
        slot_to_list.setdefault(name, name)
        return "{" + name + "}"
    if ":" in body:
        list_name, slot = (p.strip() for p in body.split(":", 1))
        list_name = _slug(list_name)
        slot = _slug(slot.lstrip("@").strip())
        slot_to_list.setdefault(slot, list_name)
        return "{" + slot + "}"
    name = _slug(body)
    slot_to_list.setdefault(name, name)
    return "{" + name + "}"


def _rewrite_slots(s: str, slot_to_list: dict[str, str]) -> str:
    return _SLOT_RE.sub(lambda m: _rewrite_slot(m.group(1), slot_to_list), s)


def _expand_rules(s: str, rules: dict[str, str], max_depth: int = 12) -> str:
    for _ in range(max_depth):
        def _sub(m: re.Match[str]) -> str:
            name = _slug(m.group(1))
            if name in rules:
                return "(" + rules[name] + ")"
            return f"<{name}>"   # rewrite the reference to its slugged form
        new = _RULE_RE.sub(_sub, s)
        if new == s or len(new) > MAX_RULE_BYTES:
            return new
        s = new
    return s


def _expand_perms(s: str) -> str:
    while True:
        m = _PERM_RE.search(s)
        if not m:
            return s
        parts = [p.strip() for p in m.group(1).split(";") if p.strip()]
        if len(parts) < 2:
            replacement = " ".join(parts)
        elif len(parts) > MAX_PERM_ELEMS:
            # bail out — n! is too big to enumerate safely
            replacement = " ".join(parts)
        else:
            orderings = [" ".join(p) for p in itertools.permutations(parts)]
            replacement = "(" + "|".join(orderings) + ")"
        s = s[: m.start()] + replacement + s[m.end():]


def _collapse_single_branch(s: str) -> str:
    """`(X)` with no top-level `|` → `X`. Balance-aware so the check is
    correct for nested groups. Subsumes `((Y))` → `(Y)` cleanup."""
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(s):
            if s[i] != "(":
                i += 1
                continue
            depth, bdepth, has_top_pipe, end = 0, 0, False, -1
            for j in range(i, len(s)):
                ch = s[j]
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = j
                        break
                elif ch == "[":
                    bdepth += 1
                elif ch == "]":
                    bdepth -= 1
                elif ch == "|" and depth == 1 and bdepth == 0:
                    has_top_pipe = True
            if end < 0:
                break
            if not has_top_pipe:
                s = s[:i] + s[i + 1 : end] + s[end + 1 :]
                changed = True
                continue
            i += 1
    return s


def _normalise_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Literal enumeration — used to promote heavy rules into entity value sets
# ---------------------------------------------------------------------------


def _match_close(s: str, start: int, opener: str, closer: str, end: int) -> int:
    depth = 0
    for j in range(start, end):
        if s[j] == opener:
            depth += 1
        elif s[j] == closer:
            depth -= 1
            if depth == 0:
                return j
    return -1


def _enum_seq(s: str, start: int, end: int, cap: int) -> list[str]:
    """Cartesian-enumerate the literal strings produced by `s[start:end]`."""
    result = [""]
    i = start
    while i < end:
        ch = s[i]
        if ch == "(":
            j = _match_close(s, i, "(", ")", end)
            if j < 0:
                break
            branches = _enum_alt(s, i + 1, j, cap)
            result = [a + b for a in result for b in branches]
            if len(result) > cap:
                raise OverflowError("enumeration cap exceeded")
            i = j + 1
        elif ch == "[":
            j = _match_close(s, i, "[", "]", end)
            if j < 0:
                break
            branches = [""] + _enum_alt(s, i + 1, j, cap)
            result = [a + b for a in result for b in branches]
            if len(result) > cap:
                raise OverflowError("enumeration cap exceeded")
            i = j + 1
        else:
            result = [a + ch for a in result]
            i += 1
    return result


def _enum_alt(s: str, start: int, end: int, cap: int) -> list[str]:
    """Split `s[start:end]` on top-level `|`, enumerate each branch."""
    branches: list[str] = []
    depth_p = depth_b = 0
    bs = start
    for i in range(start, end):
        ch = s[i]
        if ch == "(":
            depth_p += 1
        elif ch == ")":
            depth_p -= 1
        elif ch == "[":
            depth_b += 1
        elif ch == "]":
            depth_b -= 1
        elif ch == "|" and depth_p == 0 and depth_b == 0:
            branches.extend(_enum_seq(s, bs, i, cap))
            if len(branches) > cap:
                raise OverflowError("enumeration cap exceeded")
            bs = i + 1
    branches.extend(_enum_seq(s, bs, end, cap))
    return branches


def _slot_structure(s: str) -> str:
    """Strip literal text from a template, keeping only structural chars
    and `{slot}` markers — used by the adjacency / repeated-slot checks
    so they can see through nested optionals."""
    out: list[str] = []
    in_slot = False
    for ch in s:
        if in_slot:
            out.append(ch)
            if ch == "}":
                in_slot = False
        elif ch == "{":
            in_slot = True
            out.append(ch)
        elif ch in "()[]|":
            out.append(ch)
        else:
            out.append(" ")
    return "".join(out)


def _enumerate(template: str, cap: int) -> list[str]:
    """Materialise the literal value set of a slot-free template. Returns
    a sorted, deduped, whitespace-normalised list. Raises ``OverflowError``
    if the Cartesian product exceeds ``cap``. Wraps the input in a
    virtual outer alternation group so that top-level `|` (the hassil
    convention for verb tables) is treated as branch-splitting rather
    than a literal pipe character."""
    raw = _enum_alt(template, 0, len(template), cap)
    seen: dict[str, None] = {}
    for v in raw:
        v = _normalise_whitespace(v)
        if v:
            seen.setdefault(v, None)
    return sorted(seen)


def _ascii_fold(s: str) -> str:
    """Strip combining marks (á → a) and drop any remaining non-ASCII."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if ord(c) < 128 and not unicodedata.combining(c)
    )


def _slug(name: str) -> str:
    """Sanitise an identifier so OVOS-INTENT-2's `[a-z0-9_]` charset
    accepts it. Accented Latin letters fold to their base ASCII form;
    non-Latin scripts that fold to empty fall back to a stable
    hex-hash slug derived from the original name."""
    folded = _ascii_fold(name).lower()
    s = re.sub(r"[^a-z0-9_]+", "_", folded)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "x_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    elif s[0].isdigit():
        s = "x_" + s
    return s


def _snake_case(name: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return _slug(s)


def _path_violation(path: str) -> str | None:
    slots = re.findall(r"\{([^{}]+)\}", path)
    if len(slots) != len(set(slots)):
        return "repeated_slot (OVOS-INTENT-1 §3.6 forbids)"
    if re.search(r"\}\s*\{", path):
        return "adjacent_slots (OVOS-INTENT-1 §3.6 forbids)"
    return None


def _voc_looks_garbage(values: list[str]) -> bool:
    """Detect auto-promoted rules that produced meaningless particle stacks
    (e.g. 500 lines of the preposition 'на' repeated 1-4 times).

    Two signals are used:
    1. Ratio of values to unique words is very high (Cartesian-product
       explosion of a small word pool).
    2. A single short particle dominates the tokens and many values are
       just that particle repeated.
    """
    from collections import Counter
    words = [w for v in values for w in v.split()]
    if not words:
        return False
    c = Counter(words)
    # Signal 1: combinatorial blow-up of a tiny word pool
    if len(values) > 10 * len(c):
        return True
    # Signal 2: particle stacking
    most_common_word, most_common_count = c.most_common(1)[0]
    if len(most_common_word) > 4:
        return False
    if most_common_count / len(words) > 0.5:
        pure_repeats = sum(
            1 for v in values
            if set(v.split()) == {most_common_word}
        )
        if pure_repeats / len(values) > 0.2:
            return True
    return False


def rewrite_template(
    s: str, rules: dict[str, str], slot_to_list: dict[str, str]
) -> tuple[list[str] | None, str | None]:
    """Returns ``(lines, reason)``. ``lines`` is the list of output samples
    — usually one entry (the compact rewritten template), but when the
    template has *some* enumerated paths that violate OVOS-INTENT-1 §3.6
    we fall back to materialising the *valid* paths individually so the
    sample still contributes coverage instead of being dropped wholesale."""
    s = _expand_rules(s, rules)
    if len(s) > MAX_SAMPLE_BYTES:
        return None, f"sample_too_large_after_rule_inline ({len(s)}B > {MAX_SAMPLE_BYTES})"
    s = _expand_perms(s)
    if len(s) > MAX_SAMPLE_BYTES:
        return None, f"sample_too_large_after_perm_expansion ({len(s)}B > {MAX_SAMPLE_BYTES})"
    s = _rewrite_slots(s, slot_to_list)
    s = _collapse_single_branch(s)
    paths = _cartesian_paths(s)
    if paths > MAX_SAMPLE_PATHS:
        return None, f"cartesian_explosion ({paths} paths > {MAX_SAMPLE_PATHS})"

    # Check the slot-only structure: any enumerated path with adjacent or
    # repeated slots is invalid under OVOS-INTENT-1 §3.6.
    try:
        struct_paths = _enumerate(_slot_structure(s), MAX_SAMPLE_PATHS)
    except OverflowError:
        struct_paths = []
    bad_path = next((p for p in struct_paths if _path_violation(p)), None)

    if not bad_path:
        result = _normalise_whitespace(s)
        if not result:
            return None, "empty_after_rewrite"
        # The compact form itself can violate §3.6 when the same slot
        # appears in multiple branches of an alternation (e.g. fi's
        # `({area}|{area})`).  Force salvage in that case.
        if _path_violation(result):
            bad_path = result  # type: ignore[assignment]
        else:
            return [result], None

    # At least one enumerated path is invalid. Materialise the *full*
    # template (literal text included) and keep only the paths that pass
    # validation. The compact form is sacrificed, but the sample still
    # contributes the recoverable subset to the intent corpus.
    try:
        full = _enumerate(s, MAX_SAMPLE_PATHS)
    except OverflowError:
        return None, "enumeration_overflow"
    by_sig: dict[frozenset[str], list[str]] = {}
    seen: set[str] = set()
    for e in full:
        norm = _normalise_whitespace(e)
        if not norm or norm in seen or _path_violation(norm):
            continue
        seen.add(norm)
        sig = frozenset(re.findall(r"\{([^{}]+)\}", norm))
        by_sig.setdefault(sig, []).append(norm)
    if not by_sig:
        return None, "all_paths_invalid (every enumeration violates §3.6)"
    # With OVOS-INTENT-1 v3, `.intent` files allow templates with
    # different slot sets (union semantics).  Keep every valid path.
    all_valid: list[str] = []
    seen_out: set[str] = set()
    for lines in by_sig.values():
        for line in lines:
            if line not in seen_out:
                seen_out.add(line)
                all_valid.append(line)
    return all_valid, None


def _cartesian_paths(s: str) -> int:
    """Rough upper bound on enumerated sample count: at each group `(a|b)`
    multiply by (1 + pipe-count); at each `[x]` multiply by 2. Hassil
    rules often use top-level alternation (`A|B|C` with no enclosing
    parens) — we wrap in a virtual outer group so those branches are
    counted correctly."""
    paths = 1
    depth_stack: list[int] = [1]   # implicit outer group for top-level `|`
    for ch in s:
        if ch == "(":
            depth_stack.append(1)
        elif ch == ")":
            if len(depth_stack) > 1:
                paths *= depth_stack.pop()
                if paths > 10 ** 9:
                    return paths
        elif ch == "|":
            depth_stack[-1] += 1
        elif ch == "[":
            paths *= 2
            if paths > 10 ** 9:
                return paths
    # Apply the virtual outer group's branch count.
    paths *= depth_stack[0]
    return paths


# ---------------------------------------------------------------------------
# Lists / responses
# ---------------------------------------------------------------------------


def _list_values(body: dict) -> list[str] | None:
    if not isinstance(body, dict) or body.get("wildcard"):
        return None
    if body.get("values"):
        flat: list[str] = []
        for v in body["values"]:
            if isinstance(v, str):
                flat.append(v)
            elif isinstance(v, dict) and "in" in v:
                inp = v["in"]
                flat.extend(inp if isinstance(inp, list) else [inp])
        # Hassil list values are themselves templates — they can carry
        # `(...)` groups around single morphological variants that the
        # OVOS lint treats as malformed single-branch groups. Normalise
        # each value through the same collapse pass we use on samples.
        return [
            _normalise_whitespace(_collapse_single_branch(s)) or s
            for s in flat
        ] or None
    rng = body.get("range")
    if isinstance(rng, dict) and "from" in rng and "to" in rng:
        step = int(rng.get("step", 1) or 1)
        lo, hi = int(rng["from"]), int(rng["to"])
        if (hi - lo) // max(step, 1) + 1 > MAX_ENTITY_VALUES:
            return None
        return [str(n) for n in range(lo, hi + 1, step)]
    return None


def _split_jinja_if(s: str) -> list[str]:
    """Decompose `{% if … %} A {% elif … %} B {% else %} C {% endif %}`
    into branch bodies [A, B, C]. Each branch becomes a separate dialog
    phrase — the renderer picks one at random, which is a reasonable
    coarse approximation of the original conditional. Non-conditional
    text outside the if-block is prepended to each branch."""
    m_if = _JINJA_IF_RE.search(s)
    if not m_if:
        return [s]
    m_endif = _JINJA_ENDIF_RE.search(s, m_if.end())
    if not m_endif:
        return [s]
    prefix = s[: m_if.start()]
    suffix = s[m_endif.end() :]
    inside = s[m_if.end() : m_endif.start()]
    branches = _JINJA_BRANCH_RE.split(inside)
    return [prefix + b + suffix for b in branches if b.strip()]


def _normalise_response(s: str) -> tuple[list[str] | None, str | None]:
    """Returns ``(lines, reason)``. A single hassil response may decompose
    into multiple OVOS dialog phrases (one per Jinja if/elif/else branch)."""
    s = _JINJA_SET_RE.sub("", s)
    out: list[str] = []
    for branch in _split_jinja_if(s):
        # Recurse once for nested if-blocks (rare in hassil).
        sub_branches = _split_jinja_if(branch) if "{% if" in branch[len(branch) - len(branch.lstrip()):] else [branch]
        for b in sub_branches:
            b = _JINJA_SLOT_DOT_RE.sub(lambda m: "{" + m.group(1) + "}", b)
            b = _JINJA_VAR_RE.sub(lambda m: "{" + m.group(1) + "}", b)
            if _JINJA_LEFTOVER_RE.search(b):
                continue
            norm = _normalise_whitespace(b)
            if not norm or re.search(r"\}\s*\{", norm):
                continue
            slots = re.findall(r"\{([^{}]+)\}", norm)
            if len(slots) != len(set(slots)):
                continue
            # OVOS forbids slot-only templates — a dialog phrase must
            # carry at least one literal word. Drop branches that lost
            # all their literal text after Jinja stripping.
            if not re.sub(r"\{[^{}]+\}", "", norm).strip():
                continue
            out.append(norm)
    if not out:
        return None, "jinja_template_unresolvable"
    # Return all valid branches — the driver groups them by slot
    # signature and emits one .dialog file per group, so each Jinja
    # if/elif/else branch survives instead of being collapsed.
    return out, None


# ---------------------------------------------------------------------------
# Streaming I/O
# ---------------------------------------------------------------------------


class _StreamWriter:
    """Append unique non-empty lines to a file. Holds only the dedupe set
    for the currently-open file — never buffers a whole corpus."""

    def __init__(self, path: Path):
        self.path = path
        self.seen: set[str] = set()
        self.fh = None

    def write(self, line: str | None) -> None:
        if not line:
            return
        line = line.strip()
        if not line or line in self.seen:
            return
        self.seen.add(line)
        if self.fh is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.fh = self.path.open("w", encoding="utf-8")
        self.fh.write(line + "\n")

    def close(self) -> None:
        if self.fh is not None:
            self.fh.close()


def _collect_sentences(
    data: dict,
    file_rules: dict[str, str],
    canon=lambda x: x,
    canonicalize_refs=lambda x: x,
    promoted: "set[str] | None" = None,
):
    """Yields (intent_name, sample, rules) tuples one at a time, where
    `rules` is the rule set in scope for that sample — _common.yaml plus
    file-level plus per-block overrides (hassil scopes rules that way).

    Rules whose names are in ``promoted`` are skipped on re-introduction:
    a per-block expansion_rules entry that shadows an already-promoted
    `.voc` rule would otherwise undo the promotion and reinstate the
    inlined body, undoing the cartesian-explosion mitigation."""
    promoted = promoted or set()
    for name, body in (data.get("intents") or {}).items():
        for block in body.get("data", []) or []:
            block_rules = dict(file_rules)
            for rname, rtmpl in (block.get("expansion_rules") or {}).items():
                slug = _slug(canon(rname))
                if slug in promoted:
                    continue   # don't undo a global .voc promotion
                if isinstance(rtmpl, list):
                    rtmpl = "(" + "|".join(rtmpl) + ")"
                block_rules[slug] = canonicalize_refs(str(rtmpl))
            for sample in block.get("sentences", []) or []:
                yield name, sample, block_rules


def _collect_responses(data: dict):
    """Yields (intent_name, response_key, phrase). The response key (e.g.
    'default', 'lights_area') discriminates the scenario the skill code
    is responding to, so each key becomes its own .dialog file."""
    for name, body in (data.get("responses", {}).get("intents") or {}).items():
        for key, value in (body or {}).items():
            if isinstance(value, str):
                yield name, key, value
            elif isinstance(value, list):
                for v in value:
                    yield name, key, str(v)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def convert(
    src: Path,
    lang: str,
    dst: Path,
    resume: bool = True,
    report: "object | None" = None,
    check: bool = False,
) -> None:
    """Convert one language. If ``report`` is None a private TSV is opened
    next to this script; otherwise the caller's file handle is reused
    (so a multi-language run lands in a single audit log)."""
    out = dst / "locale" / lang
    out.mkdir(parents=True, exist_ok=True)

    sentences_dir = src / "sentences" / lang
    responses_dir = src / "responses" / lang
    if not sentences_dir.is_dir():
        raise SystemExit(f"no sentences for {lang!r} at {sentences_dir}")

    common: dict = {}
    common_path = sentences_dir / "_common.yaml"
    if common_path.is_file():
        common = yaml.safe_load(common_path.read_text(encoding="utf-8")) or {}

    # Lists and expansion-rule keys may be non-ASCII (e.g. Spanish
    # `habitación`, Czech `pokoj`); slug them so the OVOS lint accepts
    # the resulting resource names. All downstream code operates in
    # slug-space — `_expand_rules` and `_rewrite_slot` also slug their
    # captured names so references match up.
    #
    # Rule names additionally pass through the per-language canonical
    # name map so the resulting `.voc` files land at English topic
    # names (`turn_off.voc`, `open.voc`, …) instead of the local-
    # language original (`apaga.voc`, `obre.voc`, …).
    # Map keys are looked up in slug-space so both the accented hassil
    # original (`habitación`) and the ASCII form (`habitacion`) resolve
    # to the same canonical entry.
    lang_canonical = {
        _slug(k): v for k, v in CANONICAL_RULE_NAMES.get(lang, {}).items()
    }
    # Drop mappings whose canonical target collides with an existing
    # local rule name. E.g. in `ro/_common.yaml` both `brightness` (a
    # slot-wrapper) and `luminozitatea` (the noun) exist; mapping the
    # latter to `brightness` would silently overwrite the former when
    # the multi-source parent gets synthesised. Better to keep the
    # local name in that case and let the user resolve manually.
    existing_sources = {
        _slug(k) for k in (common.get("expansion_rules") or {})
    }
    for src in list(lang_canonical):
        target = _slug(lang_canonical[src])
        if target != src and target in existing_sources:
            del lang_canonical[src]

    def _canon(name: str) -> str:
        return lang_canonical.get(_slug(name), name)

    # `_canonicalize_refs` rewrites `<orig>` → `<canonical>` in template
    # text. When called on a rule body that belongs to a multi-source
    # canonical group, references to *sibling* sources are preserved as
    # local-named so the parent .voc can list them without creating a
    # cycle through the canonical name. The `own_canonical` argument
    # carries the rule's own group name; pass None for sample text.
    def _canonicalize_refs(s: str, own_canonical: str | None = None) -> str:
        if not lang_canonical:
            return s

        def _sub(m: re.Match[str]) -> str:
            name = m.group(1)
            target_canon = _canon(name)
            target_slug = _slug(target_canon)
            if own_canonical is not None and target_slug == own_canonical:
                # Sibling reference — keep it local so the canonical
                # parent's `<sibling>` listing terminates.
                return f"<{_slug(name)}>"
            return f"<{target_slug}>"

        return _RULE_RE.sub(_sub, s)

    lists = {_slug(k): v for k, v in (common.get("lists") or {}).items()}
    raw_rules_yaml = dict(common.get("expansion_rules") or {})

    # Hoist per-file and per-data-block `expansion_rules:` into the
    # global rule pool. Many hassil corpora define helper rules at
    # narrow scope (e.g. `quant_queda` and `dades` in `ca`'s timer
    # status block) but they're still subject to the same path-count
    # explosion when inlined. Lifting them lets the promotion pipeline
    # turn them into `.voc` files. `_common.yaml` definitions still
    # take precedence on name collision.
    for path in sorted(sentences_dir.glob("*.yaml")):
        if path.name == "_common.yaml":
            continue
        try:
            sub = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for rname, rtmpl in (sub.get("expansion_rules") or {}).items():
            raw_rules_yaml.setdefault(rname, rtmpl)
        for body in (sub.get("intents") or {}).values():
            for block in body.get("data", []) or []:
                for rname, rtmpl in (block.get("expansion_rules") or {}).items():
                    raw_rules_yaml.setdefault(rname, rtmpl)

    # Two-pass rule loading so that multiple local-language rules can
    # collapse into one canonical English concept:
    #
    #   * If only one source rule maps to a canonical name, we just
    #     rename it (existing behaviour).
    #   * If two or more source rules map to the same canonical name,
    #     each keeps its own local-named .voc file (with the synonyms
    #     intact) and we synthesise a parent .voc named after the
    #     canonical English concept whose body is `(<src1>|<src2>|...)` —
    #     the OVOS-style "vocabulary of vocabularies" pattern.
    # First pass: collect which sources map to which canonical, so we
    # can pass the right `own_canonical` context into body rewrites.
    canonical_to_sources: dict[str, list[str]] = {}
    raw_bodies: dict[str, str] = {}
    for name, template in raw_rules_yaml.items():
        if isinstance(template, list):
            template = "(" + "|".join(template) + ")"
        src_slug = _slug(name)
        can_slug = _slug(_canon(name))
        canonical_to_sources.setdefault(can_slug, []).append(src_slug)
        raw_bodies[src_slug] = (str(template), can_slug)

    raw_rules: dict[str, str] = {}
    for canonical, sources in canonical_to_sources.items():
        if len(sources) == 1:
            body, _ = raw_bodies[sources[0]]
            raw_rules[canonical] = _canonicalize_refs(body)
        else:
            # Keep each source rule under its own local name. Internal
            # `<sibling>` references stay local-named so the parent
            # composite below terminates without cycling.
            for src in sources:
                body, _ = raw_bodies[src]
                raw_rules[src] = _canonicalize_refs(body, own_canonical=canonical)
            # Add a parent rule referencing each source by local name.
            raw_rules[canonical] = "(" + "|".join(f"<{s}>" for s in sources) + ")"

    # Recursively resolve rules into final bodies. While resolving, any
    # rule whose enumerated alternation grows past PROMOTE_RULE_THRESHOLD
    # is replaced by a `{name}` slot placeholder and its literal value
    # set is captured in `promoted_values` for later `.entity` emission.
    rules: dict[str, str] = {}
    # promoted_values: rule name → enumerated literal value set. For
    # auto-promoted slot-free rules this becomes a .voc (vocabulary
    # referenced as `<name>`). FORCE_PROMOTE rules contain `{slot}`s
    # and can't be enumerated, so they go straight to free-form `{name}`
    # capture slots with no value-set file.
    promoted_values: dict[str, list[str]] = {}
    promoted_voc: set[str] = set()
    visiting: set[str] = set()

    def _resolve(name: str) -> str:
        if name in rules:
            return rules[name]
        if name in visiting:
            return f"<{name}>"   # cycle — leave unresolved
        # Hard-coded promotion: free-form capture slot, no enumeration.
        if name in FORCE_PROMOTE:
            rules[name] = "{" + name + "}"
            return rules[name]
        body = raw_rules.get(name)
        if body is None:
            return f"<{name}>"
        visiting.add(name)

        def _sub(m: re.Match[str]) -> str:
            inner = _slug(m.group(1))
            if inner not in raw_rules:
                return f"<{inner}>"   # unresolved, but slug-canonicalised
            r = _resolve(inner)
            # `{...}` or `<...>` placeholders interpolate as-is; rule
            # bodies need parens so the caller's surrounding operators
            # see one token.
            if r.startswith("{") and r.endswith("}"):
                return r
            if r.startswith("<") and r.endswith(">"):
                return r
            return "(" + r + ")"

        resolved = _RULE_RE.sub(_sub, body)
        visiting.discard(name)

        # Promotion: slot-free body + alternation count above threshold +
        # enumeration fits the entity cap.
        if "{" not in resolved:
            # The cartesian-path counter is an upper bound — it
            # over-multiplies sibling alternations. Use it only for the
            # lower-bound check, then actually attempt enumeration with
            # a cap. If enumeration fits, the rule promotes regardless
            # of how the estimator scored it.
            if _cartesian_paths(resolved) >= PROMOTE_RULE_THRESHOLD:
                try:
                    values = _enumerate(resolved, MAX_PROMOTED_VALUES)
                except OverflowError:
                    values = []
                if 0 < len(values) <= MAX_PROMOTED_VALUES:
                    if _voc_looks_garbage(values):
                        # Let it stay inlined; cartesian cap or lint will
                        # catch pathological samples later.
                        pass
                    else:
                        promoted_values[name] = values
                        promoted_voc.add(name)
                        rules[name] = f"<{name}>"
                        return rules[name]
        rules[name] = resolved
        return resolved

    for n in list(raw_rules):
        _resolve(n)
    # Auto-promoted rules emit as `.voc` and the `<name>` reference stays
    # in the sample — remove them from the inline-substitution table so
    # `_expand_rules` doesn't loop on the self-reference placeholder.
    for n in promoted_voc:
        rules.pop(n, None)

    slot_to_list: dict[str, str] = {}

    # Stats for --check mode
    stats_seen: dict[str, int] = {}
    stats_kept: dict[str, int] = {}

    # Audit log: every rejected sample/response/entity, with reason. The
    # log lives next to this script so it's easy to find and not buried
    # under the output tree.
    owns_report = report is None
    if owns_report:
        report_path = Path(__file__).resolve().parent / "convert_hassil_intents.skipped.tsv"
        report = report_path.open("w", encoding="utf-8")
        report.write("lang\tkind\tintent\treason\toriginal\n")
    else:
        report_path = Path(getattr(report, "name", "<shared>"))
    skipped = {"sample": 0, "response": 0, "entity": 0}

    def _log(kind: str, intent: str, reason: str, original: str) -> None:
        skipped[kind] = skipped.get(kind, 0) + 1
        # TSV — strip tabs/newlines from the original so each record is one row.
        clean = original.replace("\t", " ").replace("\n", " ").replace("\r", " ")
        report.write(f"{lang}\t{kind}\t{intent}\t{reason}\t{clean}\n")

    # sentences/<lang>/*.yaml → .intent (streamed)
    # OVOS-INTENT-1 v3 relaxed §5.5: `.intent` files now allow templates
    # with different slot sets (union semantics).  We stream directly to
    # one writer per target intent.  Hassil spreads samples for one
    # intent across multiple yaml files, so the writer must stay open
    # for the whole conversion.
    intent_writers: dict[Path, _StreamWriter] = {}
    skip_targets: set[Path] = set()
    try:
        for path in sorted(sentences_dir.glob("*.yaml")):
            if path.name == "_common.yaml":
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            file_rules = dict(rules)
            for rname, rtmpl in (data.get("expansion_rules") or {}).items():
                slug = _slug(_canon(rname))
                if slug in promoted_voc:
                    continue
                if isinstance(rtmpl, list):
                    rtmpl = "(" + "|".join(rtmpl) + ")"
                file_rules[slug] = _canonicalize_refs(str(rtmpl))
            for intent_name, sample, sample_rules in _collect_sentences(
                data, file_rules, _canon, _canonicalize_refs, promoted_voc
            ):
                stats_seen[intent_name] = stats_seen.get(intent_name, 0) + 1
                target = out / f"{_snake_case(intent_name)}.intent"
                if target in skip_targets:
                    continue
                if target not in intent_writers:
                    if resume and target.exists():
                        skip_targets.add(target)
                        continue
                    intent_writers[target] = _StreamWriter(target)
                sample = _canonicalize_refs(sample)
                lines, reason = rewrite_template(sample, sample_rules, slot_to_list)
                if lines is None:
                    _log("sample", intent_name, reason or "unknown", sample)
                    continue
                for line in lines:
                    intent_writers[target].write(line)
                    stats_kept[intent_name] = stats_kept.get(intent_name, 0) + 1
    finally:
        for w in intent_writers.values():
            w.close()

    # responses/<lang>/*.yaml → .dialog. A hassil response yaml has two
    # axes of variation that each become its own .dialog file:
    #
    #   * response keys (`default`, `area`, `lights_area`, …) — distinct
    #     scenarios the skill code branches on
    #   * Jinja `{% if … %} A {% elif … %} B {% else %} C {% endif %}`
    #     branches inside one response — distinct conditions the skill
    #     code also branches on
    #
    # The skill calls `self.speak_dialog(name)` with the name matching
    # the scenario + condition the runtime is in, mirroring the original
    # Jinja branch selection.
    #
    # Naming:
    #
    #     <intent>.dialog                              default key, no Jinja
    #     <intent>_branch_<N>.dialog                   default key,    Jinja
    #     <intent>_<key>.dialog                        other key,   no Jinja
    #     <intent>_<key>_branch_<N>.dialog             other key,      Jinja
    #
    # Branch indices are 1-based and follow the source order of the
    # `if`/`elif`/`else` block.
    file_lines: dict[Path, list[str]] = {}
    if responses_dir.is_dir():
        # Group raw phrases by (intent, key) first so per-key branch
        # counts are consistent across multiple list-valued entries.
        by_key: dict[tuple[str, str], list[list[str]]] = {}
        for path in sorted(responses_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for intent_name, key, phrase in _collect_responses(data):
                branches, reason = _normalise_response(phrase)
                if branches is None:
                    _log("response", intent_name, reason or "unknown", phrase)
                    continue
                by_key.setdefault((intent_name, key), []).append(branches)

        for (intent_name, key), phrase_branches in by_key.items():
            base = _snake_case(intent_name)
            key_suffix = "" if key == "default" else f"_{_snake_case(key)}"
            max_branches = max(len(b) for b in phrase_branches)
            for bi in range(max_branches):
                if max_branches == 1:
                    target = out / f"{base}{key_suffix}.dialog"
                else:
                    target = out / f"{base}{key_suffix}_branch_{bi + 1}.dialog"
                bucket = file_lines.setdefault(target, [])
                for branches in phrase_branches:
                    if bi < len(branches):
                        bucket.append(branches[bi])

    for target, lines in file_lines.items():
        if resume and target.exists():
            continue
        w = _StreamWriter(target)
        try:
            for line in lines:
                w.write(line)
        finally:
            w.close()

    # .voc — one per auto-promoted slot-free expansion rule. These are
    # vocabularies (alternations of synonyms), not capture slots.
    voc_written = 0
    for name in sorted(promoted_voc):
        target = out / f"{name}.voc"
        if resume and target.exists():
            voc_written += 1
            continue
        vw = _StreamWriter(target)
        try:
            for v in promoted_values[name]:
                vw.write(v)
        finally:
            vw.close()
        if target.exists():
            voc_written += 1

    # .entity (one per slot encountered) — streamed too.
    entities_written = 0
    for slot, list_name in sorted(slot_to_list.items()):
        target = out / f"{slot}.entity"
        if resume and target.exists():
            entities_written += 1
            continue
        # FORCE_PROMOTE rules with nested slots are free-form captures
        # — they have no materialisable value set.
        if slot in promoted_voc:
            continue   # already emitted as .voc
        body = lists.get(list_name)
        values = _list_values(body) if body is not None else None
        if not values:
            # No materialisable value set — but the slot still appears
            # in the .intent file, where OVOS treats a slot without an
            # .entity as a free-form capture. Wildcard / undefined lists
            # are expected to degrade this way, so they don't deserve a
            # row in the hard-failure audit. Only true blowups (range
            # too large to materialise, etc.) are logged.
            if isinstance(body, dict) and body.get("range"):
                _log("entity", slot, f"range_too_large (> {MAX_ENTITY_VALUES} values)", str(body))
            continue
        ew = _StreamWriter(target)
        try:
            for v in values:
                ew.write(v)
        finally:
            ew.close()
        if target.exists():
            entities_written += 1

    # Seed area.entity with common names if the language is covered and
    # the file does not already exist (e.g. from a materialised hassil list).
    area_entity = out / "area.entity"
    if not (resume and area_entity.exists()) and lang in COMMON_AREA_NAMES:
        aw = _StreamWriter(area_entity)
        try:
            for name in COMMON_AREA_NAMES[lang]:
                aw.write(name)
        finally:
            aw.close()

    if owns_report:
        report.close()
    total = sum(skipped.values())
    print(
        f"[{lang}] wrote {out} — "
        f"slots: {len(slot_to_list)}, entities: {entities_written}, "
        f"vocabularies: {voc_written}, "
        f"skipped: {skipped.get('sample', 0)}/{skipped.get('response', 0)}/"
        f"{skipped.get('entity', 0)} (sample/response/entity), "
        f"audit rows: {total}"
    )

    if check:
        thin = [
            (i, stats_seen[i], stats_kept.get(i, 0))
            for i in stats_seen
            if stats_seen[i] > 0 and stats_kept.get(i, 0) / stats_seen[i] < 0.5
        ]
        thin.sort(key=lambda x: x[2] / x[1])
        if thin:
            print(f"  --check: intents with <50% sample survival --")
            for intent, seen, kept in thin:
                print(f"    {intent}: {kept}/{seen} ({kept/seen*100:.1f}%)")


def convert_all(
    src: Path, dst: Path, resume: bool = True, check: bool = False
) -> None:
    """Convert every language under ``src/sentences/``. All languages
    share one audit TSV with a leading `lang` column."""
    sentences_root = src / "sentences"
    langs = sorted(d.name for d in sentences_root.iterdir() if d.is_dir())
    if not langs:
        raise SystemExit(f"no language directories under {sentences_root}")
    report_path = Path(__file__).resolve().parent / "convert_hassil_intents.skipped.tsv"
    with report_path.open("w", encoding="utf-8") as report:
        report.write("lang\tkind\tintent\treason\toriginal\n")
        for lang in langs:
            try:
                convert(src, lang, dst, resume=resume, report=report, check=check)
            except SystemExit as e:
                print(f"[{lang}] skipped: {e}")
    print(f"audit log: {report_path}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert OHF-Voice/intents (hassil) into an OVOS-INTENT-2 locale tree."
    )
    parser.add_argument("src", type=Path, help="Path to OHF-Voice/intents checkout")
    parser.add_argument("lang", help="Language code or 'all'")
    parser.add_argument("dst", type=Path, help="Output directory")
    parser.add_argument(
        "--check", action="store_true", help="Print coverage report per intent"
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        default=True,
        help="Overwrite existing files instead of resuming",
    )
    args = parser.parse_args()
    if args.lang == "all":
        convert_all(args.src, args.dst, resume=args.resume, check=args.check)
    else:
        convert(
            args.src, args.lang, args.dst, resume=args.resume, check=args.check
        )


if __name__ == "__main__":
    main()
