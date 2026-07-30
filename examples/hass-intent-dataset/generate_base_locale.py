"""Generate ``base_locale/`` — the single source of truth for localized
``.entity`` files across all languages.  Other scripts read from
``base_locale/`` instead of carrying hardcoded strings."""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Home Assistant internal constants (same in all languages)
# ---------------------------------------------------------------------------

HA_DOMAINS: list[str] = [
    "light", "fan", "switch", "cover", "climate", "media_player",
    "sensor", "binary_sensor", "lock", "vacuum", "timer",
    "input_boolean", "scene", "script", "automation", "weather",
    "camera", "humidifier", "water_heater",
]

HA_DEVICE_CLASSES: list[str] = [
    "awning", "blind", "curtain", "door", "garage", "gate",
    "shade", "shutter", "window", "battery", "carbon_monoxide",
    "cold", "connectivity", "gas", "heat", "light", "lock",
    "moisture", "motion", "occupancy", "opening", "plug", "power",
    "presence", "problem", "running", "safety", "smoke", "sound",
    "tamper", "update", "vibration",
]

HA_STATES: list[str] = ["on", "off", "open", "closed", "locked", "unlocked"]
COLORS_EN: list[str] = ["white", "black", "red", "orange", "yellow", "green", "blue", "purple", "brown", "pink", "turquoise"]

# ---------------------------------------------------------------------------
# Translated area names (12 common rooms per language)
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
    "hr": ["kuhinja", "dnevni boravak", "spavaća soba", "kupaonica", "ured", "garaža", "hodnik", "podrum", "blagovaonica", "vrt", "terasa", "praonica"],
    "sr": ["кухиња", "дневна соба", "спаваћа соба", "купатило", "канцеларија", "гаража", "ходник", "подрум", "трпезарија", "башта", "тераса", "вешерница"],
    "sr-Latn": ["kuhinja", "dnevna soba", "spavaća soba", "kupatilo", "kancelarija", "garaža", "hodnik", "podrum", "trpezarija", "bašta", "terasa", "vešernica"],
    "bg": ["кухня", "всекидневна", "спалня", "баня", "офис", "гараж", "коридор", "мазе", "трапезария", "градина", "тераса", "перално"],
    "uk": ["кухня", "вітальня", "спальня", "ванна", "офіс", "гараж", "коридор", "підвал", "їдальня", "сад", "тераса", "пральня"],
    "et": ["köök", "elutuba", "magamistuba", "vannituba", "kontor", "garaaž", "esik", "kelder", "söögituba", "aed", "terrass", "pesuköök"],
    "lt": ["virtuvė", "svetainė", "miegamasis", "vonios kambarys", "biuras", "garažas", "koridorius", "rūsys", "valgomasis", "sodas", "terasa", "skalbimo patalpa"],
    "lv": ["virtuve", "viesistaba", "guļamistaba", "vannasistaba", "kabinets", "garāža", "gaitenis", "pagrabstāvs", "ēdamistaba", "dārzs", "terase", "veļas mazgātava"],
    "is": ["eldhús", "stofa", "svefnherbergi", "baðherbergi", "skrifstofa", "bílskúr", "gangur", "kjallari", "borðstofa", "garður", "verönd", "þvottahús"],
    "ga": ["cistin", "seomra suí", "seomra leapa", "seomra folctha", "oifig", "garáiste", "halla", "íseallán", "seomra bia", "gairdín", "ardán", "seomra níocháin"],
    "cy": ["cegin", "ystafell fyw", "ystafell wely", "ystafell molchi", "swyddfa", "garej", "coridor", "islor", "ystafell fwyta", "gardd", "teras", "ystafell golchi"],
    "af": ["kombuis", "sitkamer", "slaapkamer", "badkamer", "kantoor", "motorhuis", "gang", "kelder", "eetkamer", "tuin", "terras", "wasgoedkamer"],
    "sw": ["jikoni", "sebule", "chumba cha kulala", "bafuni", "ofisi", "gereji", "barabara ya ukumbi", "ghorofa ya chini", "chumba cha kulia", "bustani", "mtaro", "chumba cha kufulia"],
    "eu": ["sukaldea", "egongela", "logela", "bainugela", "bulegoa", "garajea", "korridorea", "sotoa", "jangela", "lorategia", "terraza", "garbitegia"],
    "gl": ["cociña", "sala de estar", "cuarto", "baño", "oficina", "garaxe", "corredor", "soto", "comedor", "xardín", "terraza", "lavandería"],
    "fa": ["آشپزخانه", "اتاق نشیمن", "اتاق خواب", "حمام", "دفتر", "گاراژ", "راهرو", "زیرزمین", "اتاق ناهارخوری", "باغ", "تراس", "اتاق لباسشویی"],
    "ne": ["भान्सा", "बैठक कोठा", "सुत्ने कोठा", "बाथरूम", "अफिस", "ग्यारेज", "कोरिडोर", "भूमिगत", "खाना कोठा", "बगैंचा", "टेरेस", "लुगा धुने कोठा"],
    "ka": ["სამზარეულო", "მისაღები", "საძინებელი", "აბაზანა", "ოფისი", "ავტოფარეხი", "დერეფანი", "სარდაფი", "სასადილო", "ბაღი", "ტერასა", "სამრეცხაო"],
    "hi": ["रसोई", "लिविंग रूम", "बेडरूम", "बाथरूम", "कार्यालय", "गैरेज", "गलियारा", "तहखाना", "भोजन कक्ष", "बगीचा", "छत", "कपड़े धोने का कमरा"],
    "bn": ["রান্নাঘর", "বসার ঘর", "শোবার ঘর", "বাথরুম", "অফিস", "গ্যারেজ", "করিডোর", "বেসমেন্ট", "ডাইনিং রুম", "বাগান", "বারান্দা", "লন্ড্রি রুম"],
    "gu": ["રસોડું", "લિવિંગ રૂમ", "બેડરૂમ", "બાથરૂમ", "ઓફિસ", "ગેરેજ", "કોરિડોર", "ભોંયરું", "ડાઇનિંગ રૂમ", "બગીચો", "ટેરેસ", "લોન્ડ્રી રૂમ"],
    "kn": ["ಅಡುಗೆ ಮನೆ", "ದುಡಿ ಕೊಠಡಿ", "ಮಲಗು ಕೊಠಡಿ", "ಸ್ನಾನಗೃಹ", "ಕಚೇರಿ", "ಗ್ಯಾರೇಜ್", "ಕಾರಿಡಾರ್", "ನೆಲಮಾಳಿಗೆ", "ಊಟದ ಕೊಠಡಿ", "ಉದ್ಯಾನ", "ಟೆರೇಸ್", "ತೊಳೆಯುವ ಕೊಠಡಿ"],
    "ml": ["അടുക്കള", "ലിവിംഗ് റൂം", "ബെഡ്‌റൂം", "കുളിമുറി", "ഓഫീസ്", "ഗാരേജ്", "ഇടനാഴി", "ബേസ്മെൻറ്", "ഡൈനിംഗ് റൂം", "പൂന്തോട്ടം", "ടെറസ്", "ലോണ്ട്രി റൂം"],
    "mr": ["स्वयंपाकघर", "दिवाणखाना", "बेडरूम", "स्नानगृह", "कार्यालय", "गॅरेज", "कॉरिडॉर", "तळघर", "जेवणाची खोली", "बाग", "टेरेस", "लॉन्ड्री रूम"],
    "pa": ["ਰਸੋਈ", "ਲਿਵਿੰਗ ਰੂਮ", "ਬੈੱਡਰੂਮ", "ਬਾਥਰੂਮ", "ਦਫਤਰ", "ਗੈਰਾਜ", "ਕੋਰੀਡੋਰ", "ਬੇਸਮੈਂਟ", "ਡਾਇਨਿੰਗ ਰੂਮ", "ਬਾਗ", "ਛੱਤ", "ਲਾਂਡਰੀ ਰੂਮ"],
    "ta": ["சமையலறை", "பெற்று அறை", "கடுக்கை அறை", "குளியலறை", "பணி இடம்", "வாகன நிறுத்தம்", "நடைபாதை", "அடித்தளம்", "உணவு அறை", "தோட்டம்", "முற்றம்", "துவைப்பு அறை"],
    "te": ["వంటగది", "సభా గది", "నిద్ర గది", "స్నానగది", "కార్యాలయం", "గ్యారేజ్", "కారిడార్", "బేస్మెంట్", "భోజన గది", "తోట", "టెరస్", "ఉతికే గది"],
    "ur": ["باتھ روم", "بیٹھک", "سونے کا کمرہ", "باتھ روم", "دفتر", "گیراج", "گلی", "تہہ خانہ", "کھانے کا کمرہ", "باغ", "چبوترا", "دھونے کا کمرہ"],
    "mn": ["гал тогоо", "зочны өрөө", "унтлагын өрөө", "усанд орох өрөө", "оффис", "гараж", "коридор", "суурь", "хоолны өрөө", "цэцэрлэг", "терасс", "угаалгын өрөө"],
    "kw": ["kek", "rom godhesi", "kewor", "rom ymolchi", "offis", "garaj", "koryor", "kelder", "rom dybri", "lowarth", "teras", "rom yowghi"],
    "lb": ["Kichen", "Wunnzëmmer", "Schlofzëmmer", "Buedzëmmer", "Büro", "Garage", "Gank", "Keller", "Iesszëmmer", "Gaart", "Terrass", "Wäschkichen"],
}

# ---------------------------------------------------------------------------
# Translated device names per language
# ---------------------------------------------------------------------------

DEVICE_NAMES: dict[str, list[str]] = {
    "en": ["kitchen light", "living room light", "bedroom light", "ceiling fan", "thermostat", "tv", "speaker", "front door", "garage door", "vacuum"],
    "pt": ["luz da cozinha", "luz da sala", "luz do quarto", "ventilador de teto", "termostato", "televisão", "altifalante", "porta da frente", "porta da garagem", "aspirador"],
    "pt-BR": ["luz da cozinha", "luz da sala", "luz do quarto", "ventilador de teto", "termostato", "televisão", "caixa de som", "porta da frente", "porta da garagem", "aspirador"],
    "es": ["luz de la cocina", "luz del salón", "luz del dormitorio", "ventilador de techo", "termostato", "televisor", "altavoz", "puerta principal", "puerta del garaje", "aspiradora"],
    "fr": ["lumière de la cuisine", "lumière du salon", "lumière de la chambre", "ventilateur de plafond", "thermostat", "télévision", "haut-parleur", "porte d'entrée", "porte du garage", "aspirateur"],
    "de": ["Küchenlicht", "Wohnzimmerlicht", "Schlafzimmerlicht", "Deckenventilator", "Thermostat", "Fernseher", "Lautsprecher", "Eingangstür", "Garagentor", "Staubsauger"],
    "it": ["luce cucina", "luce soggiorno", "luce camera da letto", "ventilatore a soffitto", "termostato", "televisione", "altoparlante", "porta principale", "porta del garage", "aspirapolvere"],
    "nl": ["keukenverlichting", "woonkamerverlichting", "slaapkamerverlichting", "plafondventilator", "thermostaat", "televisie", "luidspreker", "voordeur", "garagedeur", "stofzuiger"],
    "pl": ["światło w kuchni", "światło w salonie", "światło w sypialni", "wentylator sufitowy", "termostat", "telewizor", "głośnik", "drzwi wejściowe", "drzwi garażowe", "odkurzacz"],
    "ru": ["свет на кухне", "свет в гостиной", "свет в спальне", "потолочный вентилятор", "термостат", "телевизор", "колонка", "входная дверь", "дверь гаража", "пылесос"],
    "ja": ["キッチンの照明", "リビングの照明", "寝室の照明", "シーリングファン", "サーモスタット", "テレビ", "スピーカー", "玄関", "ガレージのドア", "掃除機"],
    "ar": ["ضوء المطبخ", "ضوء غرفة المعيشة", "ضوء غرفة النوم", "مروحة سقف", "منظم حرارة", "تلفاز", "مكبر صوت", "الباب الأمامي", "باب المرآب", "مكنسة"],
    "zh-CN": ["厨房灯", "客厅灯", "卧室灯", "吊扇", "恒温器", "电视", "音响", "前门", "车库门", "吸尘器"],
    "zh-TW": ["廚房燈", "客廳燈", "臥室燈", "吊扇", "恆溫器", "電視", "音響", "前門", "車庫門", "吸塵器"],
    "zh-HK": ["廚房燈", "客廳燈", "睡房燈", "吊扇", "恆溫器", "電視", "音響", "大門", "車房門", "吸塵機"],
}

# ---------------------------------------------------------------------------
# Translated floor / level names per language
# ---------------------------------------------------------------------------

FLOOR_NAMES: dict[str, list[str]] = {
    "en": ["ground floor", "first floor", "second floor", "basement", "attic"],
    "pt": ["rés do chão", "primeiro andar", "segundo andar", "cave", "sótão"],
    "pt-BR": ["térreo", "primeiro andar", "segundo andar", "porão", "sótão"],
    "es": ["planta baja", "primer piso", "segundo piso", "sótano", "ático"],
    "fr": ["rez-de-chaussée", "premier étage", "deuxième étage", "sous-sol", "grenier"],
    "de": ["Erdgeschoss", "erster Stock", "zweiter Stock", "Keller", "Dachboden"],
    "it": ["piano terra", "primo piano", "secondo piano", "seminterrato", "soffitta"],
    "nl": ["begane grond", "eerste verdieping", "tweede verdieping", "kelder", "zolder"],
    "pl": ["parter", "pierwsze piętro", "drugie piętro", "piwnica", "strych"],
    "ru": ["первый этаж", "второй этаж", "третий этаж", "подвал", "чердак"],
    "ja": ["1階", "2階", "3階", "地下室", "屋根裏"],
    "ar": ["الطابق الأرضي", "الطابق الأول", "الطابق الثاني", "القبو", "العلية"],
    "zh-CN": ["一楼", "二楼", "三楼", "地下室", "阁楼"],
}

# ---------------------------------------------------------------------------
# Color and state translations (from _LANG_OVERRIDES)
# ---------------------------------------------------------------------------

COLOR_TRANSLATIONS: dict[str, list[str]] = {
    "pt": ["branco", "preto", "vermelho", "laranja", "amarelo", "verde", "azul", "roxo", "castanho", "rosa", "turquesa"],
    "pt-BR": ["branco", "preto", "vermelho", "laranja", "amarelo", "verde", "azul", "roxo", "marrom", "rosa", "turquesa"],
    "es": ["blanco", "negro", "rojo", "naranja", "amarillo", "verde", "azul", "púrpura", "marrón", "rosa", "turquesa"],
    "fr": ["blanc", "noir", "rouge", "orange", "jaune", "vert", "bleu", "violet", "marron", "rose", "turquoise"],
    "de": ["weiß", "schwarz", "rot", "orange", "gelb", "grün", "blau", "lila", "braun", "pink", "türkis"],
    "it": ["bianco", "nero", "rosso", "arancione", "giallo", "verde", "blu", "viola", "marrone", "rosa", "turchese"],
    "nl": ["wit", "zwart", "rood", "oranje", "geel", "groen", "blauw", "paars", "bruin", "roze", "turquoise"],
    "ca": ["blanc", "negre", "vermell", "taronja", "groc", "verd", "blau", "porpra", "marró", "rosa", "turquesa"],
    "da": ["hvid", "sort", "rød", "orange", "gul", "grøn", "blå", "lilla", "brun", "pink", "turkis"],
    "sv": ["vit", "svart", "röd", "orange", "gul", "grön", "blå", "lila", "brun", "rosa", "turkos"],
    "nb": ["hvit", "svart", "rød", "oransje", "gul", "grønn", "blå", "lilla", "brun", "rosa", "turkis"],
    "fi": ["valkoinen", "musta", "punainen", "oranssi", "keltainen", "vihreä", "sininen", "violetti", "ruskea", "vaaleanpunainen", "turkoosi"],
    "pl": ["biały", "czarny", "czerwony", "pomarańczowy", "żółty", "zielony", "niebieski", "fioletowy", "brązowy", "różowy", "turkusowy"],
    "ru": ["белый", "чёрный", "красный", "оранжевый", "жёлтый", "зелёный", "синий", "фиолетовый", "коричневый", "розовый", "бирюзовый"],
    "ja": ["白", "黒", "赤", "橙", "黄", "緑", "青", "紫", "茶", "桃", "水色"],
    "ko": ["흰색", "검은색", "빨간색", "주황색", "노란색", "초록색", "파란색", "보라색", "갈색", "분홍색", "청록색"],
    "zh-CN": ["白色", "黑色", "红色", "橙色", "黄色", "绿色", "蓝色", "紫色", "棕色", "粉色", "青色"],
    "ar": ["أبيض", "أسود", "أحمر", "برتقالي", "أصفر", "أخضر", "أزرق", "بنفسجي", "بني", "وردي", "تركواز"],
}

STATE_TRANSLATIONS: dict[str, list[str]] = {
    "pt": ["ligado", "desligado", "aberto", "fechado", "trancado", "destrancado"],
    "pt-BR": ["ligado", "desligado", "aberto", "fechado", "trancado", "destrancado"],
    "es": ["encendido", "apagado", "abierto", "cerrado", "bloqueado", "desbloqueado"],
    "fr": ["allumé", "éteint", "ouvert", "fermé", "verrouillé", "déverrouillé"],
    "de": ["an", "aus", "offen", "geschlossen", "verriegelt", "entriegelt"],
    "it": ["acceso", "spento", "aperto", "chiuso", "bloccato", "sbloccato"],
    "nl": ["aan", "uit", "open", "gesloten", "vergrendeld", "ontgrendeld"],
    "ca": ["encès", "apagat", "obert", "tancat", "bloquejat", "desbloquejat"],
    "da": ["til", "fra", "åben", "lukket", "låst", "oplåst"],
    "sv": ["på", "av", "öppen", "stängd", "låst", "olåst"],
    "nb": ["på", "av", "åpen", "lukket", "låst", "opplåst"],
    "fi": ["päällä", "pois", "auki", "kiinni", "lukittu", "avattu"],
    "pl": ["włączony", "wyłączony", "otwarty", "zamknięty", "zamknięty", "otwarty"],
    "ru": ["включено", "выключено", "открыто", "закрыто", "заблокировано", "разблокировано"],
    "ja": ["オン", "オフ", "開", "閉", "施錠", "解錠"],
    "ko": ["켜짐", "꺼짐", "열림", "닫힘", "잠김", "잠금해제"],
    "zh-CN": ["开", "关", "打开", "关闭", "锁定", "解锁"],
    "ar": ["مفعل", "معطل", "مفتوح", "مغلق", "مقفل", "مفتوح"],
}

LANGS: list[str] = sorted({
    "en",
    *COMMON_AREA_NAMES.keys(),
    *DEVICE_NAMES.keys(),
    *FLOOR_NAMES.keys(),
    *COLOR_TRANSLATIONS.keys(),
    *STATE_TRANSLATIONS.keys(),
})

# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def _write_entity(lang_dir: Path, name: str, values: list[str]) -> None:
    path = lang_dir / f"{name}.entity"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(values) + "\n", encoding="utf-8")


def generate_base_locale(output_dir: Path) -> int:
    written = 0
    for lang in LANGS:
        lang_dir = output_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)

        # area — translated
        areas = COMMON_AREA_NAMES.get(lang, COMMON_AREA_NAMES["en"])
        _write_entity(lang_dir, "area", areas)
        written += 1

        # name — translated or English fallback
        names = DEVICE_NAMES.get(lang, DEVICE_NAMES["en"])
        _write_entity(lang_dir, "name", names)
        written += 1

        # color — translated or English
        colors = COLOR_TRANSLATIONS.get(lang, COLORS_EN)
        _write_entity(lang_dir, "color", colors)
        written += 1

        # state — translated or English HA_STATES
        states = STATE_TRANSLATIONS.get(lang, HA_STATES)
        _write_entity(lang_dir, "state", states)
        written += 1

        # device_class / domain — HA internal identifiers (English in all langs)
        _write_entity(lang_dir, "device_class", HA_DEVICE_CLASSES)
        _write_entity(lang_dir, "domain", HA_DOMAINS)
        written += 2

        # floor — translated or English fallback
        floors = FLOOR_NAMES.get(lang, FLOOR_NAMES["en"])
        _write_entity(lang_dir, "floor", floors)
        written += 1

    return written


def main() -> None:
    import sys
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <output_dir>")
        raise SystemExit(2)
    out = Path(sys.argv[1])
    count = generate_base_locale(out)
    n_langs = len(list(out.iterdir()))
    print(f"Generated {count} .entity files across {n_langs} languages in {out}")


if __name__ == "__main__":
    main()
