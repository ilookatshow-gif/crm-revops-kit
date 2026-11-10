# Explicit local input contract / Контракт локального входа

Use `crm-revops-kit --json schema` for the machine-readable schema and the
[six-case fixture](../examples/synthetic-handoffs.json) for a complete input.
This document explains the meaning of those fields. The accepted input is this
module's JSON format, not an arbitrary CRM vendor export.

`crm-revops-kit --json schema` выводит машинную схему, а
[учебный файл](../examples/synthetic-handoffs.json) содержит полный вход.
Ниже объясняется смысл полей. Произвольную выгрузку CRM нужно сначала привести
к этому контракту по разрешённым данным, сохранив происхождение и пробелы.

## Fields / Поля

All object keys are exact; extra keys and duplicate JSON keys are rejected.
Все ключи объектов заданы явно; лишние и повторяющиеся ключи запрещены.

| Location | Required fields and meaning / Обязательные поля и смысл |
|---|---|
| Root | `schema_version: 1`; explicit offset-aware `as_of`; integer `max_snapshot_age_hours` from 1 to 168; `snapshot`, `handoffs`, `acknowledgements` |
| `snapshot` | `captured_at`, declared boolean `complete`, `deals` array. Completeness is supplied, not provider-verified. Полнота заявлена в файле и не проверена у провайдера. |
| Snapshot deal | `deal_id`, `owner_id`, `stage`: bounded nonblank strings; unique deal ID. Строковые ID и этап, без пустых значений и дублей сделок. |
| Handoff | Unique `id`, unique `deal_id`, `from_owner_id`, different `to_owner_id`, `target_stage`, `prepared_at`, `next_step`, nonempty `evidence`. Одна передача на сделку, отправитель отличается от получателя. |
| `next_step` | `description`, `due_at`; due time must be later than preparation. Описание и срок после времени подготовки. |
| Evidence item | `id`, `source_ref`, `summary`; supplied reference and summary are not fetched or verified. Программа не открывает и не проверяет источник. |
| Acknowledgement | `handoff_id`, `accepted_by`, `accepted_at`, `decision` as `accepted` or `rejected`, `packet_sha256`, `note` (may be empty). At most one per known handoff. Не больше одного ответа на известную передачу. |

UTF-8 JSON is bounded to 1 MiB before parsing. Nonstandard NaN/Infinity values,
boolean values in integer fields, control characters and oversized values are
rejected rather than silently shortened. `schema` gives the precise string and
collection bounds. An invalid file produces exit 2 and no new report.

До разбора проверяется предел 1 МиБ UTF-8. NaN/Infinity, логические значения
вместо целых чисел, управляющие символы и превышение лимитов отклоняются;
содержимое не сокращается молча. Точные пределы строк и коллекций показывает
`schema`. При некорректном файле программа завершится с кодом 2 без нового отчёта.

## Packet identity / Версия пакета

The fingerprint is SHA-256 of the complete handoff object encoded as:

```python
json.dumps(handoff, sort_keys=True, ensure_ascii=True,
           separators=(',', ':'), allow_nan=False).encode('utf-8')
```

Algorithm name: `sha256/json-sort-keys-ensure-ascii-compact-v1`.
`fingerprint` returns that canonical JSON and the digest for each packet. The
snapshot and acknowledgement are excluded. Every handoff field, including
evidence order, is included. Object-key order is normalised; array order is not.

Хеш считается по полному объекту передачи. Снимок и ответ в него не входят;
поля передачи и порядок её списков входят. Порядок ключей объектов
нормализуется. Команда `fingerprint` отдаёт канонический JSON и хеш. Сохранённый
хеш указывает версию текста; он не удостоверяет личность, чтение или истинность.

## Time and scope / Время и область

Use the module's deliberately strict RFC3339-style subset: uppercase `T` and
`Z`, required seconds, an optional fraction of 1–6 digits, and `Z` or a known
numeric timezone offset. Offset minutes must be 00–59. The unknown offset
`-00:00`, leap seconds and year 0000 are not supported. This is a bounded input
profile, not acceptance of every valid RFC3339 representation. Comparisons use
UTC; the computer's current time is not substituted. `max_snapshot_age_hours`
is a user-selected policy input, not a universal sales or CRM standard.

Формат времени намеренно уже RFC3339: прописные `T` и `Z`, обязательные секунды,
необязательная дробная часть из 1–6 цифр, `Z` или известное числовое смещение.
Минуты смещения — 00–59. Неизвестное смещение `-00:00`, високосные секунды и год
0000 не поддерживаются. Сравнение выполняется в UTC; текущее время компьютера
не подставляется. Предел возраста снимка выбирает пользователь для задачи,
а не универсальная норма продаж или CRM.

The snapshot must be complete by declaration, not future-dated or stale, and
not earlier than the packet or its supplied acknowledgement to establish the
post-handoff owner/stage. A missing deal is a review finding. A future packet
or receipt cannot establish an event at an earlier observation time.

Для проверки ответственного и этапа после передачи снимок должен быть заявлен
полным, не быть будущим или просроченным и не предшествовать пакету и его
предоставленному ответу. Отсутствующая сделка требует проверки. Будущий пакет
или ответ не устанавливают событие на более ранний момент.

## Finding codes / Коды причин

| Code | Meaning / Значение |
|---|---|
| `SNAPSHOT_INCOMPLETE` | Scope is declared incomplete / Заявлена неполная область |
| `SNAPSHOT_STALE` | Snapshot exceeds the chosen age / Снимок старше выбранного предела |
| `SNAPSHOT_FUTURE` | Snapshot is later than as_of / Снимок позже момента проверки |
| `SNAPSHOT_BEFORE_HANDOFF` | Snapshot predates the packet / Снимок раньше пакета |
| `SNAPSHOT_BEFORE_ACK` | Snapshot predates the acknowledgement / Снимок раньше ответа |
| `DEAL_NOT_IN_SNAPSHOT` | Deal is absent from the supplied snapshot / Сделки нет в предоставленном снимке |
| `OWNER_MISMATCH` | Usable snapshot owner differs from receiver / Ответственный в пригодном снимке отличается от получателя |
| `STAGE_MISMATCH` | Usable snapshot stage differs from target / Этап в пригодном снимке отличается от целевого |
| `PACKET_FUTURE` | Packet was prepared after as_of / Пакет подготовлен позже момента проверки |
| `NEXT_STEP_OVERDUE` | Next-step due time has passed / Срок следующего шага прошёл |
| `ACK_MISSING` | No acknowledgement supplied / Подтверждение не предоставлено |
| `ACK_REJECTED` | Supplied decision is rejection / В ответе указан отказ |
| `ACK_HASH_MISMATCH` | Receipt refers to another packet version / Ответ относится к другой версии |
| `ACK_ACTOR_MISMATCH` | Supplied receiver ID differs / ID принявшего отличается от получателя |
| `ACK_BEFORE_PACKET` | Receipt predates packet preparation / Ответ раньше подготовки пакета |
| `ACK_FUTURE` | Receipt is later than as_of / Ответ позже момента проверки |

Several codes may apply to one row. They are observations about the supplied
data, not instructions to reassign a deal or contact a customer. No findings
means `consistent`; any finding means `needs_review`. All rows are audited.

У одной строки может быть несколько причин. Это наблюдения по предоставленным
данным, а не команды переназначить сделку или написать клиенту. Без причин
строка получает `consistent`, с любой причиной — `needs_review`. Проверяются
все передачи.

## Output / Выход

With `--json`, success is a JSON object with `ok`, `command` and `version`.
Audit reports include `evidence_basis`, `as_of`, `input_sha256`, snapshot
metadata, summary counts and rows with handoff/deal IDs, packet SHA-256,
classification and finding codes. Fingerprint reports contain canonical JSON
and packet digests. Error JSON has `ok:false`; do not parse diagnostic wording
as a business result.

В отчёте есть основание проверки, момент наблюдения, SHA-256 полного входного
файла, сведения о снимке, счётчики и все строки с кодами причин. Успешный
технический разбор данных не означает успешную передачу сделки. Код1 для
корректного отчёта с причинами нужно сохранить; код2 означает ошибку входа или
выполнения. `demo` добавляет `synthetic:true` и не доказывает результат клиента.
