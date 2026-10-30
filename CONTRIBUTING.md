# Contributing to Robot Skills (RS)

RS is at an early draft stage, so the most useful contributions right now are reviews and ideas.

## Ways to help

- **Review the spec.** Open an issue for anything unclear, missing or wrong in [`spec/rs-spec-v0.1.md`](spec/rs-spec-v0.1.md). The "Open questions" section lists where input is most needed.
- **Write an example skill.** Pick an everyday task and write it in the RS grammar. Examples show quickly where the format is too weak or too complicated.
- **Propose a class code or capability.** Open an issue with the proposed code (for example `RS 6.3.2`), a name, a one-line definition and an example skill.
- **Bring a robotics view.** If you work with robots, simulators, motion primitives or standards such as VDI 2860, your experience is very valuable.

## Using AI assistants

You are welcome to use AI assistants to review drafts or suggest changes. Please say so in the issue or pull request and check what the assistant wrote before submitting it.

## Pull requests

1. Open an issue first for anything larger than a typo, so the change can be discussed.
2. Keep each pull request to one topic.
3. Spec text uses **must**, **should** and **may** for required, recommended and optional.

## Validator development

The initial reference toolchain is Python 3.11 or later. See
[the validator guide](docs/validator.md) for installation, the bounded authoring
profile and read/write APIs. Run `python -m unittest discover -s tests -v` after
installing the package. Changes to accepted source shapes must update the
packaged JSON Schema, semantic checks, profile documentation and regression
tests together. Do not equate static authoring validity with safe robot execution.

## Licence

By contributing, you agree that your contribution is licensed under the [Apache License 2.0](LICENSE). Example skills in this repository are covered by the same licence.
