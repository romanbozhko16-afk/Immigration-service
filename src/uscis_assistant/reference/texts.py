"""Fixed reference-chat texts in Russian, Ukrainian and English."""

# Rule 6 of AGENTS.md: this exact English label appears on every reference answer.
OFFICIAL_LABEL = "Reference information from official USCIS sources. Not legal advice."

MESSAGES: dict[str, dict[str, str]] = {
    "label": {
        "ru": "Справочная информация из официальных источников USCIS. Не юридическая консультация.",
        "uk": "Довідкова інформація з офіційних джерел USCIS. Не юридична консультація.",
        "en": OFFICIAL_LABEL,
    },
    "quotes_header": {
        "ru": "Вот что говорит официальный текст (на английском, без перевода):",
        "uk": "Ось що каже офіційний текст (англійською, без перекладу):",
        "en": "Here is what the official text says:",
    },
    "footer": {
        "ru": "Если вам нужен ответ применительно к вашей ситуации, обратитесь к юристу: вы можете запросить проверку кейса юристом-партнёром.",
        "uk": "Якщо вам потрібна відповідь щодо вашої ситуації, зверніться до юриста: ви можете замовити перевірку кейсу юристом-партнером.",
        "en": "For an answer about your own situation, please ask an attorney; you can request a review by a partner attorney.",
    },
    "no_answer": {
        "ru": "Я не нашёл ответа в официальных источниках, которые у меня есть. Не знаю — пожалуйста, уточните у юриста.",
        "uk": "Я не знайшов відповіді в офіційних джерелах, які в мене є. Не знаю — будь ласка, уточніть у юриста.",
        "en": "I could not find an answer in the official sources I have. I don't know; please ask an attorney.",
    },
    "declined": {
        "ru": "Я не могу давать юридические советы: оценивать ваши шансы, говорить, подходите ли вы, или подсказывать, какую категорию или форму выбрать. Это может сделать только юрист. Вы можете запросить проверку вашего кейса юристом-партнёром. Я могу показать, что говорят официальные инструкции USCIS по общему вопросу о форме.",
        "uk": "Я не можу надавати юридичні поради: оцінювати ваші шанси, казати, чи підходите ви, або підказувати, яку категорію чи форму обрати. Це може зробити лише юрист. Ви можете замовити перевірку вашого кейсу юристом-партнером. Я можу показати, що кажуть офіційні інструкції USCIS щодо загального питання про форму.",
        "en": "I can't give legal advice: I can't assess your chances, say whether you qualify, or tell you which category or form to choose. Only an attorney can do that. You can request a review of your case by a partner attorney. I can show what the official USCIS instructions say about a general question on the form.",
    },
    "off_topic": {
        "ru": "Я отвечаю только на общие вопросы о форме I-765 по официальным источникам USCIS.",
        "uk": "Я відповідаю лише на загальні питання про форму I-765 за офіційними джерелами USCIS.",
        "en": "I only answer general questions about Form I-765 from official USCIS sources.",
    },
    "unavailable": {
        "ru": "Справочный чат сейчас недоступен. Попробуйте позже или обратитесь к юристу.",
        "uk": "Довідковий чат зараз недоступний. Спробуйте пізніше або зверніться до юриста.",
        "en": "The reference chat is unavailable right now. Please try again later or ask an attorney.",
    },
    "page": {"ru": "стр.", "uk": "с.", "en": "page"},
}
