# Check that a sales handoff still matches its acknowledgement

**CRM RevOps Kit** checks a local handoff packet, the acknowledgement referring
to that packet, and a supplied CRM snapshot. It flags a changed packet, a missing
or rejected acknowledgement, a different owner or stage, an overdue next step,
and evidence that cannot establish the state at the chosen time.

The result is a review queue for one handoff process. `consistent` means the
supplied fields agree. A hash does not prove that a person reviewed the packet,
that a source is true, or that a customer agreed to a next step.

Python 3.9+, standard library only. Runs offline without an account, API key,
model or paid core. It reads the module's explicit JSON contract; it does not
import every CRM export format, fetch source references, contact people or
change a CRM.

Prepared by **Дмитрий Лукашов / Dmitry Lukashov**, as a standalone component of
the [Lookatshow system for AI agents](https://github.com/ilookatshow-gif/lookatshow-open-tools).
[Русский](README.ru.md) · [MIT](LICENSE) · [Authorship and rights](NOTICE.md)

## Run the teaching batch

Unpack the v0.1.0 release archive into a new directory. From that directory:

```bash
python3 -B crm_revops_kit.py --json doctor
python3 -B crm_revops_kit.py --json fingerprint examples/synthetic-handoffs.json
python3 -B crm_revops_kit.py --json audit examples/synthetic-handoffs.json
```

The six handoffs are invented. The fixture fixes `as_of` at
`2026-11-10T09:00:00+03:00`; there is no implicit current wall clock. One row is
consistent and five need review:

| Case | What the audit should expose |
|---|---|
| Complete matching packet, receipt and usable snapshot | `consistent` |
| No acknowledgement | `ACK_MISSING` |
| Packet edited after the acknowledged version | `ACK_HASH_MISMATCH` |
| Snapshot shows another owner | `OWNER_MISMATCH` |
| Next-step due time has passed | `NEXT_STEP_OVERDUE` |
| Receiver rejected the packet | `ACK_REJECTED` |

[Input](examples/synthetic-handoffs.json) · [Actual generated report](examples/synthetic-report.json).
The fixture is a teaching case, not client data, a measured model response or a
Lookatshow sales result.

`audit` and `demo` return **exit 1** when a valid report contains review items.
That is the expected result for this example. Exit 0 means every supplied row
is consistent; exit 2 means invalid input or an execution error. Inspect the
JSON and the exit code together. Do not use a blanket `|| true` in automation.

## Install the command

On POSIX, choose a new prefix and command directory:

```bash
python3 -B install.py --prefix "$HOME/.local/share/crm-revops-kit" --bin-dir "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"
cd /tmp
crm-revops-kit --json doctor
crm-revops-kit --json demo
```

The installer makes a separate runtime copy and a launcher using the Python
interpreter that ran it. Existing installation or command paths are preserved;
choose another path if they are occupied. Keep that interpreter available and
store your own input and reports outside the prefix.

The native installer supports POSIX. On Windows run the source CLI with
`python crm_revops_kit.py ...`, substituting your installed Python command for
`python3`. A CI configuration is separate from an actual native-host result.

Optional `crm-revops-kit --json onboard` shows the author's links once and
creates a local `.onboarded` marker. Ordinary JSON and saved audit reports have
no promotional inserts or telemetry.

Remove the installation from any directory using its original two paths:

```bash
python3 -B "$HOME/.local/share/crm-revops-kit/uninstall.py" --prefix "$HOME/.local/share/crm-revops-kit" --bin-dir "$HOME/.local/bin"
```

The uninstaller verifies owned-file hashes and preserves other user files.
Inspect a modified or incomplete installation before attempting removal again.

## Check your own handoff

Read the [input contract](docs/INPUT-CONTRACT.md) and the
[handoff workflow](docs/HANDOFF-WORKFLOW.md). Prepare an authorised local JSON
file outside the installation. Set its explicit observation time and chosen
snapshot-age limit. Keep the actual source records available to the reviewer.

```bash
crm-revops-kit --json schema
crm-revops-kit --json fingerprint ./handoffs.json
crm-revops-kit --json audit ./handoffs.json --output ./handoff-review.json
```

The fingerprint command returns canonical packet JSON and its SHA-256. A
receiver can record acceptance or rejection of that exact version in the
input's `acknowledgements` collection after reviewing it through the team's
authorised process. Changing any handoff field changes the fingerprint. The
CLI does not create or authenticate a person's acknowledgement.

A saved report contains the same audit JSON as stdout. Existing output is
preserved unless `--replace` is selected explicitly. Input/output path or
hard-link collisions are rejected. Choose real paths without symlinked parent
directories; a symlinked output parent is refused. Invalid input does not
create a report.

`snapshot.complete` is supplied metadata. An incomplete, stale, future or
earlier snapshot cannot establish the post-handoff owner and stage. Missing
deals become review items; they are not evidence that no CRM record exists.
Times are compared in UTC, including explicit offsets. A future receipt cannot
satisfy a check made before that receipt existed.

## Give an agent a bounded task

> Use CRM RevOps Kit on this authorised local JSON. Run doctor, then fingerprint
> and audit. Preserve the audit exit code: 1 is a valid report needing review.
> Show every finding and its handoff ID. Explain what each supplied source can
> establish at as_of and what remains unknown. Do not infer customer consent,
> identity, source truth, payment or actual CRM delivery. Do not change the
> packet, generate acknowledgements, contact anyone or write to CRM. Return the
> saved report path and the human check needed for each unresolved handoff.

The [repo-local skill](skills/crm-revops-kit/SKILL.md) gives the same operation
order for agents that can run local Python commands. It is not an MCP server
or a claim of certified compatibility with every agent host.

[Bitrix Read Kit](https://github.com/ilookatshow-gif/bitrix-read-kit) addresses a
different step: reading visible CRM activities with explicit scope. CRM RevOps
Kit checks supplied handoff consistency. Neither a visible activity nor a
matching receipt establishes the complete customer lifecycle.

## Learning and implementation

Prepared by **Дмитрий Лукашов**. [Practical AI notes](https://t.me/lookatsoul).
To learn this process on your own task, see
[personal learning](https://lookatshow.ru/executive?utm_source=github&utm_medium=open_module&utm_campaign=crm-revops-kit&utm_content=readme_learn).
To discuss a process or integration project, use
[implementation](https://lookatshow.ru/ai-implementation/?utm_source=github&utm_medium=open_module&utm_campaign=crm-revops-kit&utm_content=readme_implementation).
Training and implementation have separate scopes. The free module requires no
subscription, contact details or purchase.
