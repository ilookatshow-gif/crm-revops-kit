# One handoff, an exact packet and an observable outcome

[Русский ниже](#передача-сделки-пакет-подтверждение-и-наблюдаемый-результат).
This is an original process template for one sales handoff. Adapt the roles,
time limits and actual source requirements to the team's authorised process.
The module checks the supplied representation; it does not run the CRM process.

| Step | Responsible role | Required input and guard | Saved result |
|---|---|---|---|
| Prepare the packet | Sender | Stable handoff/deal IDs, different sender and receiver IDs, target stage, explicit preparation time, next step and due time, source references and summaries | Versioned packet outside the public package |
| Identify the version | Sender or local operator | Validate the complete JSON, run `fingerprint`; preserve the exact handoff content | Canonical packet JSON and SHA-256 |
| Review and accept or reject | Assigned receiver | Read the actual evidence through the team's permitted channel; check the task, owner, stage and next step. The digest must refer to the reviewed version | Recorded acceptance/rejection, receiver identity reference, time, packet digest and note |
| Make a scoped CRM change, if assigned | Authorised CRM operator | Check the real account, deal and existing state. Save the intended operation before one write; read back the exact outcome | Provider object/state and time, kept separately from the local audit |
| Capture the observation | Authorised exporter | Obtain a snapshot at or after the packet and acknowledgement. Declare what the export covers and whether it is complete. Choose `as_of` and a maximum snapshot age | Supplied snapshot and source provenance |
| Audit all packets | Local operator | `audit INPUT --output NEW_REPORT`; preserve exit0/1/2 and the exact input version | Complete local JSON report with input and packet hashes |
| Resolve exceptions | Process owner and receiver | Open the source behind each finding, assign one concrete correction and preserve the history | Human decision and the next observable check |

The receiver's acknowledgement belongs to the team's actual identity and
communication process. Writing a string in `accepted_by` or copying a digest
into JSON does not create that real acknowledgement. Keep the original receipt
where the reviewer can inspect it; the CLI only checks supplied fields.

When an outcome is unknown, reconcile it with the real system before another
write. A timeout does not establish that an operation failed. This module has
no provider write or retry command.

## Read the queue without erasing uncertainty

- `ACK_MISSING`: obtain or locate the actual response. Do not invent acceptance.
- `ACK_HASH_MISMATCH`: compare the reviewed packet with the changed one. Preserve
  the old receipt and seek a response to the new version through the assigned
  process. Do not edit the old receipt's hash to make the check pass.
- `ACK_REJECTED`: read the receiver's reason and resolve the handoff. A technical
  checksum cannot overrule the rejection.
- `OWNER_MISMATCH` or `STAGE_MISMATCH`: verify the exact real deal and current
  state. A matching name or a supplied ID does not grant authority to reassign it.
- An unusable snapshot or absent deal: establish scope and obtain suitable
  evidence. Do not call absence in an export proof that the CRM has no record.
- `NEXT_STEP_OVERDUE`: verify whether the step happened, was rescheduled or is
  still due. The due time is not evidence that a customer agreed or attended.

A corrected packet is a new version. Recompute its fingerprint, obtain the
appropriate actual review, capture later CRM evidence and run the audit again.
Keep the earlier input/report; do not rewrite history to manufacture a clean
status.

## What closes the task

`consistent` closes the local consistency check only. To close an operational
handoff, the process owner still needs the actual reviewed packet, identifiable
receiver response, appropriate current CRM readback and the agreed next action.
Choose those requirements for the real process; this template does not verify
customer consent, data completeness or payment. A signed contract, a customer
conversation and money received are separate evidence objects.

## Передача сделки: пакет, подтверждение и наблюдаемый результат

Это оригинальный шаблон одного процесса передачи сделки. Роли, допустимый
возраст данных и требования к источникам выбирает команда для своей задачи.
Модуль проверяет предоставленное описание процесса и не выполняет его в CRM.

| Шаг | Кто отвечает | Что проверить до действия | Что сохранить |
|---|---|---|---|
| Собрать пакет | Передающий | Постоянные ID передачи и сделки, разные ID отправителя и получателя, целевой этап, время подготовки, следующий шаг и срок, ссылки на основания и их краткое содержание | Версию пакета вне публичного репозитория |
| Зафиксировать версию | Передающий или локальный оператор | Проверить полный JSON и выполнить `fingerprint`, сохранив точное содержание передачи | Канонический JSON пакета и SHA-256 |
| Принять или отклонить | Назначенный получатель | Прочитать реальные основания через разрешённый канал, проверить задачу, ответственного, этап и следующий шаг. Хеш относится к прочитанной версии | Реальный ответ, ссылка на личность получателя, время, хеш пакета и примечание |
| Выполнить порученное изменение CRM | Уполномоченный оператор CRM | Проверить кабинет, сделку и исходное состояние. До одной записи сохранить намерение, после неё прочитать точный результат | Состояние объекта провайдера и время отдельно от локального отчёта |
| Снять состояние | Уполномоченный исполнитель выгрузки | Получить снимок не раньше пакета и ответа, указать область и заявленную полноту. Выбрать `as_of` и предел возраста снимка | Снимок и происхождение исходных данных |
| Проверить все передачи | Локальный оператор | Выполнить `audit INPUT --output NEW_REPORT`, сохранить код0/1/2 и точную версию входа | Полный JSON-отчёт с хешами входа и пакетов |
| Разобрать исключения | Владелец процесса и получатель | Открыть основание каждой причины, назначить одно конкретное исправление и сохранить историю | Решение человека и следующий проверяемый шаг |

Подтверждение получателя возникает в реальном процессе общения и проверки
личности. Строка `accepted_by` и вставленный в JSON хеш его не создают.
Сохраните исходный ответ там, где проверяющий сможет его прочитать. CLI только
сопоставляет предоставленные поля.

Если исход изменения неизвестен, сначала выясните его в реальной системе.
Тайм-аут не доказывает, что запись не состоялась. У модуля нет команды записи
в CRM или повторной отправки.

### Как разобрать причины

- `ACK_MISSING`: найдите или получите реальный ответ, не достраивайте согласие.
- `ACK_HASH_MISMATCH`: сопоставьте принятую и изменённую версии. Сохраните старый
  ответ и получите реакцию на новую версию по назначенному процессу. Не
  подменяйте хеш в прежнем ответе ради зелёного отчёта.
- `ACK_REJECTED`: прочитайте причину отказа и разберите передачу. Совпавшая
  контрольная сумма не отменяет отказ получателя.
- `OWNER_MISMATCH` или `STAGE_MISMATCH`: проверьте конкретную реальную сделку и
  её состояние. Совпавшее имя или предоставленный ID не дают полномочий на
  переназначение.
- Непригодный снимок или отсутствующая сделка: выясните область выгрузки и
  получите подходящее свидетельство. Отсутствие в файле не доказывает отсутствие
  записи в CRM.
- `NEXT_STEP_OVERDUE`: уточните, выполнен ли шаг, перенесён или ещё ожидается.
  Срок не подтверждает договорённость с клиентом или состоявшийся разговор.

Правка пакета создаёт новую версию. Пересчитайте хеш, проведите нужную реальную
проверку, получите более позднее состояние CRM и повторите аудит. Сохраните
прежние вход и отчёт; не переписывайте историю для получения чистого статуса.

### Что считается завершением

`consistent` завершает локальную проверку согласованности. Для завершения самой
передачи владелец процесса проверяет прочитанный пакет, идентифицируемый ответ
получателя, подходящее состояние CRM и следующий согласованный шаг. Требования
задаются для конкретной задачи: этот шаблон не удостоверяет согласие клиента,
полноту данных или оплату. Договор, состоявшийся разговор и поступившие деньги
подтверждаются отдельно.
