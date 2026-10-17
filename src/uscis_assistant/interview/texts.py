"""Fixed interface texts in Russian, Ukrainian and English."""

from uscis_assistant.interview.bank import Language

YES = {"ru": {"да", "д"}, "uk": {"так", "т"}, "en": {"yes", "y"}}
NO = {"ru": {"нет", "н"}, "uk": {"ні", "н"}, "en": {"no", "n"}}
# Answers meaning "I have none / it does not apply" for optional questions.
NONE_WORDS = {"ru": {"нет", "-"}, "uk": {"немає", "ні", "-"}, "en": {"none", "no", "-"}}
DONT_KNOW = {
    "ru": {"не знаю"},
    "uk": {"не знаю"},
    "en": {"i don't know", "i do not know", "don't know"},
}
HELP_REQUEST = {"?", "help", "помощь", "допомога"}

DATE_FORMAT: dict[Language, str] = {"ru": "ДД.ММ.ГГГГ", "uk": "ДД.ММ.РРРР", "en": "MM/DD/YYYY"}

MESSAGES: dict[str, dict[Language, str]] = {
    "empty": {
        "ru": "Ответ пустой. Пожалуйста, ответьте на вопрос.",
        "uk": "Відповідь порожня. Будь ласка, дайте відповідь на питання.",
        "en": "The answer is empty. Please answer the question.",
    },
    "yes_no": {
        "ru": "Пожалуйста, ответьте «да» или «нет».",
        "uk": "Будь ласка, дайте відповідь «так» або «ні».",
        "en": 'Please answer "yes" or "no".',
    },
    "choice": {
        "ru": "Пожалуйста, выберите номер одного из вариантов.",
        "uk": "Будь ласка, оберіть номер одного з варіантів.",
        "en": "Please choose the number of one of the options.",
    },
    "date": {
        "ru": "Не удалось понять дату. Введите её в формате ДД.ММ.ГГГГ, например 05.10.1967.",
        "uk": "Не вдалося зрозуміти дату. Введіть її у форматі ДД.ММ.РРРР, наприклад 05.10.1967.",
        "en": "Could not read the date. Enter it as MM/DD/YYYY, for example 10/05/1967.",
    },
    "state": {
        "ru": "Введите двухбуквенный код штата США, например NY или CA.",
        "uk": "Введіть двобуквений код штату США, наприклад NY або CA.",
        "en": "Enter the two-letter U.S. state code, for example NY or CA.",
    },
    "latin": {
        "ru": "Пожалуйста, напишите латиницей, точно как в ваших документах.",
        "uk": "Будь ласка, напишіть латиницею, точно як у ваших документах.",
        "en": "Please type it in Latin letters, exactly as in your documents.",
    },
    "translation_pending": {
        "ru": "Записано. Ответ будет переведён на английский, и мы попросим вас проверить перевод.",
        "uk": "Записано. Відповідь буде перекладено англійською, і ми попросимо вас перевірити переклад.",
        "en": "Saved. The answer will be translated into English and you will be asked to check it.",
    },
    "saved": {"ru": "Записано.", "uk": "Записано.", "en": "Saved."},
    "help_header": {
        "ru": "Официальный текст инструкции USCIS (на английском, без перевода):",
        "uk": "Офіційний текст інструкції USCIS (англійською, без перекладу):",
        "en": "Official USCIS text:",
    },
    "source": {"ru": "Источник", "uk": "Джерело", "en": "Source"},
    "optional_hint": {
        "ru": "Если у вас этого нет — напишите «нет».",
        "uk": "Якщо у вас цього немає — напишіть «немає».",
        "en": 'If this does not apply, type "none".',
    },
    "yes_no_hint": {"ru": "(да / нет)", "uk": "(так / ні)", "en": "(yes / no)"},
    "date_hint": {
        "ru": "Формат: ДД.ММ.ГГГГ",
        "uk": "Формат: ДД.ММ.РРРР",
        "en": "Format: MM/DD/YYYY",
    },
    "help_hint": {
        "ru": "Напишите «?», чтобы увидеть официальный текст инструкции.",
        "uk": "Напишіть «?», щоб побачити офіційний текст інструкції.",
        "en": 'Type "?" to see the official instruction text.',
    },
    "done": {
        "ru": "Все вопросы заданы.",
        "uk": "Усі питання поставлено.",
        "en": "All questions have been asked.",
    },
    "decline_advice": {
        "ru": "Я не могу давать юридические советы: оценивать ваши шансы, говорить, подходите ли вы, или подсказывать, какую категорию или форму выбрать. Это может сделать только юрист. Вы можете запросить проверку вашего кейса юристом-партнёром. А сейчас вернёмся к вопросу формы.",
        "uk": "Я не можу надавати юридичні поради: оцінювати ваші шанси, казати, чи підходите ви, або підказувати, яку категорію чи форму обрати. Це може зробити лише юрист. Ви можете замовити перевірку вашого кейсу юристом-партнером. А зараз повернімося до питання форми.",
        "en": "I can't give legal advice: I can't assess your chances, say whether you qualify, or tell you which category or form to choose. Only an attorney can do that. You can request a review of your case by a partner attorney. Let's continue with the form question.",
    },
    "form_question": {
        "ru": "Я могу показать официальный текст инструкции USCIS к этому вопросу — напишите «?». Ответ применительно к вашей ситуации может дать только юрист: вы можете запросить проверку кейса юристом-партнёром.",
        "uk": "Я можу показати офіційний текст інструкції USCIS до цього питання — напишіть «?». Відповідь щодо вашої ситуації може дати лише юрист: ви можете замовити перевірку кейсу юристом-партнером.",
        "en": 'I can show the official USCIS instruction text for this question: type "?". Only an attorney can answer for your specific situation; you can request a review by a partner attorney.',
    },
    "rephrase": {
        "ru": "Похоже, это вопрос, а не ответ. Если это ответ — напишите его без знака «?». Чтобы увидеть официальный текст инструкции, напишите «?».",
        "uk": "Схоже, це питання, а не відповідь. Якщо це відповідь — напишіть її без знака «?». Щоб побачити офіційний текст інструкції, напишіть «?».",
        "en": 'This looks like a question rather than an answer. If it is an answer, type it without "?". To see the official instruction text, type "?".',
    },
    "translation_confirm": {
        "ru": "Для формы ответ нужен на английском. Предлагаемый вариант: «{english}» (ваш ответ: «{original}»). Если верно — напишите «да». Если нет — напишите правильный вариант латиницей.",
        "uk": "Для форми відповідь потрібна англійською. Запропонований варіант: «{english}» (ваша відповідь: «{original}»). Якщо правильно — напишіть «так». Якщо ні — напишіть правильний варіант латиницею.",
        "en": 'The form needs this answer in English. Suggested: "{english}" (your answer: "{original}"). If correct, type "yes". If not, type the correct version in Latin letters.',
    },
    "type_latin": {
        "ru": "Для формы этот ответ нужен на английском (латиницей). Ваш ответ: «{original}». Напишите его, пожалуйста, латиницей.",
        "uk": "Для форми ця відповідь потрібна англійською (латиницею). Ваша відповідь: «{original}». Напишіть її, будь ласка, латиницею.",
        "en": 'The form needs this answer in English (Latin letters). Your answer: "{original}". Please type it in Latin letters.',
    },
}
