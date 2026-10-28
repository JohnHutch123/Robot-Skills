# Robot Skills (RS)

An open, platform-independent format for packaging humanoid robot skills, such as opening a bottle or ironing a shirt, as compact, signed, nestable packets.

> **Status:** early draft (v0.1). Everything here is open for discussion. Please open an issue with comments, questions or ideas.

## The idea

A skill should be something you can hand from one robot to another, like a recipe:

- **Portable.** A skill describes *what* to do and *where things move relative to objects*, not the joint angles of one robot. Each robot maps it onto its own body.
- **Compact.** A typical skill packet is a few kilobytes. Movements are stored as small mathematical motion primitives, not recordings.
- **Nestable.** A skill can call other skills, so "iron a shirt" can reuse "grasp an object" and "lay a garment flat".
- **Learnable.** A robot downloads a skill, tries it, adapts it to its own tools and keeps what it learns. Improvements can be published back as *variants*.
- **Trustworthy.** Every skill carries provenance (author, dates, origin, tests) and is signed by its author and, once tested, by the library.
- **Open to everyone.** Skills can be written by hand or recorded from a person using everyday equipment (camera, microphone), tested in simulation and shared through an open library.

## What a skill looks like

```text
rs 0.1

skill open-bottle-with-opener 1.0.0 {
  id      0192f3a4-7c1e-7b2a-9d4e-5a1f6c3b8e20   # global ID (UUID v7), same for all versions
  title   "Open a capped bottle with a bottle opener"
  class   RS 2.1.2                        # Changing quantity > Divide > Detach a part
  tags    object:bottle tool:bottle-opener body:two-hands domain:kitchen
  needs   ArmMotion x2, GripperMotion x2, Grasping, ForceSensing, Camera

  pre     upright(bottle), capped(bottle), reachable(opener)
  effect  not capped(bottle)
  success not capped(bottle) and upright(bottle) within 30 s

  plan sequence {
    use grasp-object >=1.0 (target: bottle.neck, hand: left)
    use grasp-object >=1.0 (target: opener.handle, hand: right)
    position opener.lip to bottle.cap.rim  motion: approach
    retry 3 {
      rotate opener about opener.lip by 25 deg  motion: lever  force <= 40 N
      check not capped(bottle)
    }
    release opener
  }
  ...
}
```

The full example is in [`examples/skills/`](examples/skills/).

## Repository layout

| Path | Contents |
| --- | --- |
| [`spec/rs-spec-v0.1.md`](spec/rs-spec-v0.1.md) | The draft specification |
| [`docs/prior-art.md`](docs/prior-art.md) | Survey of existing systems and storage options, and why RS is designed this way |
| [`examples/skills/`](examples/skills/) | Example skills in RS text and YAML form |
| [`examples/robots/`](examples/robots/) | Example robot capability profiles |
| [`docs/library-database.md`](docs/library-database.md) | Design of the open skill library: global IDs, fast lookup, ratings, usage and comments |
| [`library/`](library/) | SQL schema, example queries and sample data for the library (PostgreSQL) |

## Key design choices (v0.1)

- **Grammar:** a small text language (`.rsk`), with YAML accepted as an alternative. Both compile to a binary packet (`.rsp`).
- **Binary packet:** deterministic CBOR ([RFC 8949](https://www.rfc-editor.org/rfc/rfc8949)), signed with COSE ([RFC 9052](https://www.rfc-editor.org/rfc/rfc9052)) and Ed25519.
- **Action words:** based on the handling functions of VDI 2860 (storing, changing quantity, moving, securing, checking), plus a few RS additions.
- **Robot capabilities:** based on RoboEarth's Semantic Robot Description Language (SRDL).
- **Classification:** open-ended `RS` class codes (like a library catalogue) plus searchable tags.
- **Global IDs:** every skill has a UUID v7 that travels with it; every published version also has a content hash.
- **Open library:** a relational database ranks skills by measured success rate, how many robots use them, and ratings, with comments on each version.

## Roadmap

1. ~~Survey prior art and storage options~~ ([docs/prior-art.md](docs/prior-art.md))
2. Core spec v0.1 (draft in progress: [spec/rs-spec-v0.1.md](spec/rs-spec-v0.1.md))
3. Worked examples: ironing a shirt (nested skills) and a locally adapted variant
4. Tooling plan: record a person, generate a skill, test it in a simulator, publish it to an open library, and a 3D viewer

## Contributing

Ideas, reviews and criticism are very welcome, from people and from AI assistants alike. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

- The specification, examples and tools in this repository are licensed under the [Apache License 2.0](LICENSE).
- Skills published to the RS library default to [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Authors may choose [CC0](https://creativecommons.org/publicdomain/zero/1.0/) instead.
