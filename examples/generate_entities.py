"""Generate .entity files for all slots that lack them across the
hassil-locale tree.  Populates language-specific value sets where
possible and falls back to English for universal HA constants."""
from __future__ import annotations

import json
import os
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Slot value definitions
# ---------------------------------------------------------------------------

# Numeric ranges — same digits in every language
NUMERIC_SLOTS: dict[str, range] = {
    "brightness": range(0, 101),
    "percentage": range(0, 101),
    "position": range(0, 101),
    "volume_level": range(0, 101),
    "volume_step": range(1, 21),
    "temperature": range(0, 101),
    "hours": range(0, 24),
    "minutes": range(0, 60),
    "seconds": range(0, 60),
    "start_hours": range(0, 24),
    "start_minutes": range(0, 60),
}

# Home Assistant internal state values (language-agnostic constants)
HA_STATES: list[str] = [
    "on", "off", "open", "closed", "locked", "unlocked",
    "opening", "closing", "detected", "clear", "charging",
    "not_charging", "connected", "disconnected", "home",
    "away", "running", "not_running", "safe", "unsafe",
    "update_available", "up_to_date", "low", "normal",
    "wet", "dry", "cold", "hot", "present", "not_present",
]

HA_DOMAINS: list[str] = [
    "light", "fan", "switch", "cover", "climate", "media_player",
    "sensor", "binary_sensor", "lock", "vacuum", "timer",
    "input_boolean", "scene", "script", "automation",
    "weather", "camera", " humidifier", "water_heater",
]

HA_DEVICE_CLASSES: list[str] = [
    "awning", "blind", "curtain", "door", "garage", "gate",
    "shade", "shutter", "window", "battery", "carbon_monoxide",
    "cold", "connectivity", "door", "garage_door", "gas", "heat",
    "light", "lock", "moisture", "motion", "occupancy", "opening",
    "plug", "power", "presence", "problem", "running", "safety",
    "smoke", "sound", "tamper", "update", "vibration",
]

COLORS: list[str] = [
    "white", "black", "red", "orange", "yellow", "green",
    "blue", "purple", "brown", "pink", "turquoise",
]

MEDIA_CLASSES: list[str] = [
    "artist", "album", "track", "song", "playlist",
    "podcast", "movie", "tv_show",
]

# Temporal expressions — English examples (best-effort; translators can localize)
TIMER_DURATIONS: list[str] = [
    "1 minute", "5 minutes", "10 minutes", "15 minutes",
    "30 minutes", "1 hour", "2 hours", "3 hours",
]

TIMER_STARTS: list[str] = [
    "in 1 minute", "in 5 minutes", "in 10 minutes",
    "in 1 hour", "in 2 hours", "at 3 pm", "at noon",
]

# Common device name patterns (examples; real devices are user-defined)
DEVICE_NAME_EXAMPLES: list[str] = [
    "kitchen light", "living room light", "bedroom light",
    "front door", "garage door", "back gate",
    "thermostat", "tv", "speaker",
]

# Shopping / todo items
ITEM_EXAMPLES: list[str] = [
    "milk", "bread", "eggs", "coffee", "apples",
]

# Free-form examples
MESSAGE_EXAMPLES: list[str] = [
    "hello", "dinner is ready", "the laundry is done",
]

SEARCH_QUERY_EXAMPLES: list[str] = [
    "the beatles", "jazz", "news",
]

CONVERSATION_COMMAND_EXAMPLES: list[str] = [
    "remind me to call mom", "set a timer",
]

RESPONSE_EXAMPLES: list[str] = [
    "yes", "no", "ok", "sure",
]

FLOOR_EXAMPLES: list[str] = [
    "ground floor", "first floor", "second floor", "basement", "attic",
]

# ---------------------------------------------------------------------------
# Per-language overrides (where we have translations)
# ---------------------------------------------------------------------------

_LANG_OVERRIDES: dict[str, dict[str, list[str]]] = {
    # Portuguese (PT) — examples
    "pt": {
        "state": ["ligado", "desligado", "aberto", "fechado", "trancado", "destrancado"],
        "color": ["branco", "preto", "vermelho", "laranja", "amarelo", "verde", "azul", "roxo", "castanho", "rosa", "turquesa"],
    },
    "pt-BR": {
        "state": ["ligado", "desligado", "aberto", "fechado", "trancado", "destrancado"],
        "color": ["branco", "preto", "vermelho", "laranja", "amarelo", "verde", "azul", "roxo", "marrom", "rosa", "turquesa"],
    },
    "es": {
        "state": ["encendido", "apagado", "abierto", "cerrado", "bloqueado", "desbloqueado"],
        "color": ["blanco", "negro", "rojo", "naranja", "amarillo", "verde", "azul", "púrpura", "marrón", "rosa", "turquesa"],
    },
    "fr": {
        "state": ["allumé", "éteint", "ouvert", "fermé", "verrouillé", "déverrouillé"],
        "color": ["blanc", "noir", "rouge", "orange", "jaune", "vert", "bleu", "violet", "marron", "rose", "turquoise"],
    },
    "de": {
        "state": ["an", "aus", "offen", "geschlossen", "verriegelt", "entriegelt"],
        "color": ["weiß", "schwarz", "rot", "orange", "gelb", "grün", "blau", "lila", "braun", "pink", "türkis"],
    },
    "it": {
        "state": ["acceso", "spento", "aperto", "chiuso", "bloccato", "sbloccato"],
        "color": ["bianco", "nero", "rosso", "arancione", "giallo", "verde", "blu", "viola", "marrone", "rosa", "turchese"],
    },
    "nl": {
        "state": ["aan", "uit", "open", "gesloten", "vergrendeld", "ontgrendeld"],
        "color": ["wit", "zwart", "rood", "oranje", "geel", "groen", "blauw", "paars", "bruin", "roze", "turquoise"],
    },
    "ca": {
        "state": ["encès", "apagat", "obert", "tancat", "bloquejat", "desbloquejat"],
        "color": ["blanc", "negre", "vermell", "taronja", "groc", "verd", "blau", "porpra", "marró", "rosa", "turquesa"],
    },
    "da": {
        "state": ["til", "fra", "åben", "lukket", "låst", "oplåst"],
        "color": ["hvid", "sort", "rød", "orange", "gul", "grøn", "blå", "lilla", "brun", "pink", "turkis"],
    },
    "sv": {
        "state": ["på", "av", "öppen", "stängd", "låst", "olåst"],
        "color": ["vit", "svart", "röd", "orange", "gul", "grön", "blå", "lila", "brun", "rosa", "turkos"],
    },
    "nb": {
        "state": ["på", "av", "åpen", "lukket", "låst", "opplåst"],
        "color": ["hvit", "svart", "rød", "oransje", "gul", "grønn", "blå", "lilla", "brun", "rosa", "turkis"],
    },
    "fi": {
        "state": ["päällä", "pois", "auki", "kiinni", "lukittu", "avattu"],
        "color": ["valkoinen", "musta", "punainen", "oranssi", "keltainen", "vihreä", "sininen", "violetti", "ruskea", "vaaleanpunainen", "turkoosi"],
    },
    "pl": {
        "state": ["włączony", "wyłączony", "otwarty", "zamknięty", "zamknięty", "otwarty"],
        "color": ["biały", "czarny", "czerwony", "pomarańczowy", "żółty", "zielony", "niebieski", "fioletowy", "brązowy", "różowy", "turkusowy"],
    },
    "ru": {
        "state": ["включено", "выключено", "открыто", "закрыто", "заблокировано", "разблокировано"],
        "color": ["белый", "чёрный", "красный", "оранжевый", "жёлтый", "зелёный", "синий", "фиолетовый", "коричневый", "розовый", "бирюзовый"],
    },
    "ja": {
        "state": ["オン", "オフ", "開", "閉", "施錠", "解錠"],
        "color": ["白", "黒", "赤", "橙", "黄", "緑", "青", "紫", "茶", "桃", "水色"],
    },
    "ko": {
        "state": ["켜짐", "꺼짐", "열림", "닫힘", "잠김", "잠금해제"],
        "color": ["흰색", "검은색", "빨간색", "주황색", "노란색", "초록색", "파란색", "보라색", "갈색", "분홍색", "청록색"],
    },
    "zh-CN": {
        "state": ["开", "关", "打开", "关闭", "锁定", "解锁"],
        "color": ["白色", "黑色", "红色", "橙色", "黄色", "绿色", "蓝色", "紫色", "棕色", "粉色", "青色"],
    },
    "ar": {
        "state": ["مفعل", "معطل", "مفتوح", "مغلق", "مقفل", "مفتوح"],
        "color": ["أبيض", "أسود", "أحمر", "برتقالي", "أصفر", "أخضر", "أزرق", "بنفسجي", "بني", "وردي", "تركواز"],
    },
    "he": {
        "state": ["דלוק", "כבוי", "פתוח", "סגור", "נעול", "פתוח"],
        "color": ["לבן", "שחור", "אדום", "כתום", "צהוב", "ירוק", "כחול", "סגול", "חום", "ורוד", "טורקיז"],
    },
    "tr": {
        "state": ["açık", "kapalı", "açık", "kapalı", "kilitli", "kilitli açık"],
        "color": ["beyaz", "siyah", "kırmızı", "turuncu", "sarı", "yeşil", "mavi", "mor", "kahverengi", "pembe", "turkuaz"],
    },
    "th": {
        "state": ["เปิด", "ปิด", "เปิด", "ปิด", "ล็อค", "ปลดล็อค"],
        "color": ["ขาว", "ดำ", "แดง", "ส้ม", "เหลือง", "เขียว", "น้ำเงิน", "ม่วง", "น้ำตาล", "ชมพู", "ฟ้า"],
    },
    "vi": {
        "state": ["bật", "tắt", "mở", "đóng", "khóa", "mở khóa"],
        "color": ["trắng", "đen", "đỏ", "cam", "vàng", "xanh lá", "xanh dương", "tím", "nâu", "hồng", "ngọc"],
    },
    "id": {
        "state": ["hidup", "mati", "terbuka", "tertutup", "terkunci", "terbuka"],
        "color": ["putih", "hitam", "merah", "oranye", "kuning", "hijau", "biru", "ungu", "coklat", "merah muda", "biru toska"],
    },
    "ms": {
        "state": ["hidup", "mati", "buka", "tutup", "kunci", "buka"],
        "color": ["putih", "hitam", "merah", "oren", "kuning", "hijau", "biru", "ungu", "perang", "merah jambu", "biru turquoise"],
    },
    "ro": {
        "state": ["pornit", "oprit", "deschis", "închis", "blocat", "deblocat"],
        "color": ["alb", "negru", "roșu", "portocaliu", "galben", "verde", "albastru", "mov", "maro", "roz", "turcoaz"],
    },
    "el": {
        "state": ["ανοικτό", "κλειστό", "ανοικτό", "κλειστό", "κλειδωμένο", "ξεκλείδωτο"],
        "color": ["λευκό", "μαύρο", "κόκκινο", "πορτοκαλί", "κίτρινο", "πράσινο", "μπλε", "μωβ", "καφέ", "ροζ", "τυρκουάζ"],
    },
    "hu": {
        "state": ["be", "ki", "nyitva", "zárva", "zárva", "nyitva"],
        "color": ["fehér", "fekete", "piros", "narancssárga", "sárga", "zöld", "kék", "lila", "barna", "rózsaszín", "türkiz"],
    },
    "cs": {
        "state": ["zapnuto", "vypnuto", "otevřeno", "zavřeno", "zamčeno", "odemčeno"],
        "color": ["bílá", "černá", "červená", "oranžová", "žlutá", "zelená", "modrá", "fialová", "hnědá", "růžová", "tyrkysová"],
    },
    "sk": {
        "state": ["zapnuté", "vypnuté", "otvorené", "zatvorené", "zamknuté", "odomknuté"],
        "color": ["biela", "čierna", "červená", "oranžová", "žltá", "zelená", "modrá", "fialová", "hnedá", "ružová", "tyrkysová"],
    },
    "sl": {
        "state": ["vklopljeno", "izklopljeno", "odprto", "zaprto", "zaklenjeno", "odklenjeno"],
        "color": ["bela", "črna", "rdeča", "oranžna", "rumena", "zelena", "modra", "vijolična", "rjava", "roza", "turkizna"],
    },
    "hr": {
        "state": ["uključeno", "isključeno", "otvoreno", "zatvoreno", "zaključano", "otključano"],
        "color": ["bijela", "crna", "crvena", "narančasta", "žuta", "zelena", "plava", "ljubičasta", "smeđa", "ružičasta", "tirkizna"],
    },
    "sr": {
        "state": ["укључено", "искључено", "отворено", "затворено", "закључано", "откључано"],
        "color": ["бела", "црна", "црвена", "наранџаста", "жута", "зелена", "плава", "љубичаста", "смеђа", "ружа", "тиркизна"],
    },
    "sr-Latn": {
        "state": ["uključeno", "isključeno", "otvoreno", "zatvoreno", "zaključano", "otključano"],
        "color": ["bela", "crna", "crvena", "narandžasta", "žuta", "zelena", "plava", "ljubičasta", "smeđa", "ružičasta", "tirkizna"],
    },
    "bg": {
        "state": ["включено", "изключено", "отворено", "затворено", "заключено", "отключено"],
        "color": ["бял", "черен", "червен", "оранжев", "жълт", "зелен", "син", "лилав", "кафяв", "розов", "тюркоаз"],
    },
    "uk": {
        "state": ["увімкнено", "вимкнено", "відкрито", "закрито", "заблоковано", "розблоковано"],
        "color": ["білий", "чорний", "червоний", "помаранчевий", "жовтий", "зелений", "синій", "фіолетовий", "коричневий", "рожевий", "бірюзовий"],
    },
    "et": {
        "state": ["sees", "väljas", "avatud", "suletud", "lukustatud", "avatud"],
        "color": ["valge", "must", "punane", "oranž", "kollane", "roheline", "sinine", "lilla", "pruun", "roosa", "türkiis"],
    },
    "lt": {
        "state": [["įjungta", "išjungta", "atidaryta", "uždaryta", "užrakinta", "atrakinta"]],
        "color": ["balta", "juoda", "raudona", "oranžinė", "geltona", "žalia", "mėlyna", "violetinė", "rudа", "rožinė", "turkio"],
    },
    "lv": {
        "state": ["ieslēgts", "izslēgts", "atvērts", "aizvērts", "aizslēgts", "atslēgts"],
        "color": ["balts", "melns", "sarkans", "oranžs", "dzeltens", "zaļš", "zils", "violets", "brūns", "rozā", "tirkīzs"],
    },
    "is": {
        "state": ["á", "af", "opið", "lokað", "læst", "opnað"],
        "color": ["hvítur", "svartur", "rauður", "appelsínugulur", "gulur", "grænn", "blár", "fjólublár", "brúnn", "bleikur", "grænblár"],
    },
    "ga": {
        "state": ["ar", "as", "oscailte", "dúnta", "faoi ghlas", "oscailte"],
        "color": ["bán", "dubh", "dearg", "oraiste", "buí", "glas", "gorm", "corcra", "donn", "bándearg", "turcais"],
    },
    "cy": {
        "state": ["ymlaen", "i ffwrdd", "agored", "ar gau", "wedi'i gloi", "wedi'i datgloi"],
        "color": ["gwyn", "du", "coch", "oren", "melyn", "gwyrdd", "glas", "porffor", "brown", "pinc", "torcwys"],
    },
    "af": {
        "state": ["aan", "af", "oop", "toe", "gesluit", "oopgesluit"],
        "color": ["wit", "swart", "rooi", "oranje", "geel", "groen", "blou", "pers", "bruin", "pienk", "turkoois"],
    },
    "sw": {
        "state": ["wazi", "zima", "funguliwa", "fungwa", "kufungwa", "kufunguliwa"],
        "color": ["nyeupe", "nyeusi", "nyekundu", "machungwa", "manjano", "kijani", "bluu", "zambarau", "kahawia", "waridi", "turquoise"],
    },
    "eu": {
        "state": ["piztuta", "itzalita", "irekita", "itxita", "blokeatuta", "desblokeatuta"],
        "color": ["zuri", "beltz", "gorri", "laranja", "hori", "berde", "urdin", "more", "marroi", "arrosa", "turkesa"],
    },
    "gl": {
        "state": ["encendido", "apagado", "aberto", "pechado", "bloqueado", "desbloqueado"],
        "color": ["branco", "negro", "vermello", "laranxa", "amarelo", "verde", "azul", "púrpura", "marrón", "rosa", "turquesa"],
    },
    "fa": {
        "state": ["روشن", "خاموش", "باز", "بسته", "قفل شده", "باز شده"],
        "color": ["سفید", "سیاه", "قرمز", "نارنجی", "زرد", "سبز", "آبی", "بنفش", "قهوه‌ای", "صورتی", "فیروزه‌ای"],
    },
    "ne": {
        "state": ["खुला", "बन्द", "खुला", "बन्द", "बन्द", "खुला"],
        "color": ["सेतो", "कालो", "रातो", "सुन्तला", "पहेँलो", "हरियो", "नीलो", "प्याजी", "खैरो", "गुलाबी", "हरियो नीलो"],
    },
    "ka": {
        "state": ["ჩართული", "გამორთული", "გახსნილი", "დახურული", "დაკეტილი", "გახსნილი"],
        "color": ["თეთრი", "შავი", "წითელი", "ნარინჯისფერი", "ყვითელი", "მწვანე", "ლურჯი", "იისფერი", "ყავისფერი", "ვარდისფერი", "ფირუზისფერი"],
    },
    "bn": {
        "state": ["চালু", "বন্ধ", "খোলা", "বন্ধ", "বন্ধ", "খোলা"],
        "color": ["সাদা", "কালো", "লাল", "কমলা", "হলুদ", "সবুজ", "নীল", "বেগুনি", "বাদামি", "গোলাপি", "ফিরোজা"],
    },
    "gu": {
        "state": ["ચાલુ", "બંધ", "ખુલ્લું", "બંધ", "બંધ", "ખુલ્લું"],
        "color": ["સફેદ", "કાળો", "લાલ", "નારંગી", "પીળો", "લીલો", "વાદળી", "વાયલેટ", "તપખમ", "ગુલાબી", "ફિરોઝા"],
    },
    "hi": {
        "state": ["चालू", "बंद", "खुला", "बंद", "बंद", "खुला"],
        "color": ["सफेद", "काला", "लाल", "नारंगी", "पीला", "हरा", "नीला", "बैंगनी", "भूरा", "गुलाबी", "फिरोजा"],
    },
    "kn": {
        "state": ["ಆನ್", "ಆಫ್", "ತೆರೆ", "ಮುಚ್ಚು", "ಮುಚ್ಚು", "ತೆರೆ"],
        "color": ["ಬಿಳಿ", "ಕಪ್ಪ", "ಕೆಂಪು", "ಕಿಟಕಿ", "ಹಳದಿ", "ಹಸಿರು", "ನೀಲಿ", "ನೇರಳೆ", "ಕಂದು", "ಗುಲಾಬಿ", "ಟರ್ಕಿಶ್"],
    },
    "ml": {
        "state": ["ഓൺ", "ഓഫ്", "തുറന്ന", "അടച്ച", "പൂട്ടിയ", "തുറന്ന"],
        "color": ["വെള്ള", "കറുപ്പ്", "ചുവപ്പ്", "ഓറഞ്ച്", "മഞ്ഞ", "പച്ച", "നീല", "ഊദ", "തവിട്ട്", "ചുവപ്പ്", "പച്ചനീല"],
    },
    "mr": {
        "state": ["चालू", "बंद", "उघड", "बंद", "बंद", "उघड"],
        "color": ["पांढरा", "काळा", "लाल", "केशरी", "पिवळा", "हिरवा", "निळा", "जांभळा", "तपकिरी", "गुलाबी", "फिरोजा"],
    },
    "pa": {
        "state": ["ਚਾਲੂ", "ਬੰਦ", "ਖੁੱਲ੍ਹਾ", "ਬੰਦ", "ਬੰਦ", "ਖੁੱਲ੍ਹਾ"],
        "color": ["ਚਿੱਟਾ", "ਕਾਲਾ", "ਲਾਲ", "ਨਾਰੰਗੀ", "ਪੀਲਾ", "ਹਰਾ", "ਨੀਲਾ", "ਜਾਮਨੀ", "ਭੂਰਾ", "ਗੁਲਾਬੀ", "ਫਿਰੋਜ਼ਾ"],
    },
    "ta": {
        "state": ["இயக்கத்தில்", "அணை", "திறந்த", "மூடிய", "பூட்டிய", "திறந்த"],
        "color": ["வெள்ளை", "கருப்பு", "சிவப்பு", "செம்மஞ்சள்", "மஞ்சள்", "பச்சை", "நீலம்", "ஊதா", "பழுப்பு", "சிவப்பு", "கடல் பச்சை"],
    },
    "te": {
        "state": ["ఆన్", "ఆఫ్", "తెరిచిన", "మూసిన", "మూసిన", "తెరిచిన"],
        "color": ["తెలుపు", "నలుపు", "ఎరుపు", "నారింజ", "పసుపు", "ఆకుపచ్చ", "నీలం", "ఊదా", "ముదురు", "ఎరుపు", "ఆకుపచ్చ నీలం"],
    },
    "ur": {
        "state": ["آن", "آف", "کھلا", "بند", "بند", "کھلا"],
        "color": ["سفید", "سیاہ", "سرخ", "نارنجی", "پیلا", "سبز", "نیلا", "بنفشی", "بھورا", "گلابی", "فیروزی"],
    },
    "mn": {
        "state": ["ассан", "унтраасан", "нээгдсэн", "хаалттай", "түгжсэн", "нээгдсэн"],
        "color": ["цагаан", "хар", "улаан", "улбар шар", "шар", "ногоон", "хөх", "хөхөвтөр", "бор", "ягаан", "түрquoise"],
    },
    "kw": {
        "state": ["yn-mara", "marow", "ygerys", "degesys", "gwlyk", "digorys"],
        "color": ["gwynn", "du", "rudh", "oren", "melyn", "glas", "glas", "glas", "gwyrdh", "gwyrdh", "glas"],
    },
    "lb": {
        "state": ["un", "aus", "op", "zou", "gespaart", "op"],
        "color": ["wäiss", "schwaarz", "rout", "orange", "giel", "gréng", "blo", "mof", "brong", "rosa", "turkoois"],
    },
    "pl": {
        "state": ["włączony", "wyłączony", "otwarty", "zamknięty", "zamknięty", "otwarty"],
        "color": ["biały", "czarny", "czerwony", "pomarańczowy", "żółty", "zielony", "niebieski", "fioletowy", "brązowy", "różowy", "turkusowy"],
    },
}

# Fix lt state
if "lt" in _LANG_OVERRIDES:
    _LANG_OVERRIDES["lt"]["state"] = ["įjungta", "išjungta", "atidaryta", "uždaryta", "užrakinta", "atrakinta"]


def _get_values(slot: str, lang: str) -> list[str] | None:
    """Return a value list for ``slot`` in ``lang``, or ``None`` if the slot
    should remain a free-form wildcard."""
    # Check language-specific overrides first
    overrides = _LANG_OVERRIDES.get(lang, {})
    if slot in overrides:
        return overrides[slot]

    # Numeric ranges
    if slot in NUMERIC_SLOTS:
        return [str(n) for n in NUMERIC_SLOTS[slot]]

    # Universal HA constants
    if slot == "state":
        return HA_STATES
    if slot == "domain":
        return HA_DOMAINS
    if slot == "device_class":
        return HA_DEVICE_CLASSES
    if slot == "color":
        return COLORS
    if slot == "media_class":
        return MEDIA_CLASSES

    # Temporal (English examples as fallback)
    if slot == "timer_duration":
        return TIMER_DURATIONS
    if slot == "timer_start":
        return TIMER_STARTS

    # Example-based slots (return examples rather than leaving empty)
    if slot == "name":
        return DEVICE_NAME_EXAMPLES
    if slot == "item":
        return ITEM_EXAMPLES
    if slot == "message":
        return MESSAGE_EXAMPLES
    if slot == "search_query":
        return SEARCH_QUERY_EXAMPLES
    if slot == "conversation_command":
        return CONVERSATION_COMMAND_EXAMPLES
    if slot == "response":
        return RESPONSE_EXAMPLES
    if slot == "floor":
        return FLOOR_EXAMPLES

    # Unknown slot — leave as wildcard (no .entity file)
    return None


def generate_missing_entities(locale_dir: Path) -> dict[str, int]:
    """Walk the locale tree and write ``.entity`` files for every slot that
    appears in ``.intent`` files but has no matching ``.entity`` file."""
    stats: dict[str, int] = {}
    langs = [d for d in locale_dir.iterdir() if d.is_dir()]

    for lang_dir in sorted(langs):
        lang = lang_dir.name
        intent_files = list(lang_dir.glob("*.intent"))
        if not intent_files:
            continue

        # Discover which slots are used
        used_slots: set[str] = set()
        for intent_file in intent_files:
            with intent_file.open(encoding="utf-8") as fh:
                for line in fh:
                    for match in re.finditer(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", line):
                        used_slots.add(match.group(1))

        written = 0
        for slot in sorted(used_slots):
            entity_path = lang_dir / f"{slot}.entity"
            if entity_path.exists():
                continue
            values = _get_values(slot, lang)
            if values is None:
                continue
            with entity_path.open("w", encoding="utf-8") as fh:
                for v in values:
                    fh.write(v + "\n")
            written += 1

        if written:
            stats[lang] = written

    return stats


import re

def main() -> None:
    import sys
    if len(sys.argv) != 2:
        print("Usage: python generate_entities.py <locale_dir>")
        raise SystemExit(2)
    locale_dir = Path(sys.argv[1])
    stats = generate_missing_entities(locale_dir)
    total = sum(stats.values())
    print(f"Wrote {total} .entity files across {len(stats)} languages.")
    for lang, count in sorted(stats.items()):
        print(f"  {lang:8}: {count} files")


if __name__ == "__main__":
    main()
