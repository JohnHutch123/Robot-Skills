# Prior Art and Storage Options

Survey dated 2026-10-26. It explains why RS is designed the way it is.

## Summary

No universal, compact skill packet for humanoid robots exists today. The closest earlier attempt was RoboEarth (EU-funded, about 2009 to 2014), which shared "action recipes" between robots. It was tied to a heavy ontology stack and is no longer maintained. Current standards work, such as ISO/WD 26264-1 (June 2026), covers humanoid training data, not skills.

Recommendation: do not invent everything from scratch. Use a layered packet with four parts:
- a small readable skill language for the steps and conditions;
- mathematical motion primitives for movement;
- optional learned models attached separately;
- a compact binary encoding for transport.

Borrow the step structure from behavior trees, the precondition and effect idea from PDDL, the capability-versus-skill split from Industrie 4.0, and the robot-capability matching idea from RoboEarth.

## Existing systems

Each existing system solves one slice of the problem; none packages steps, motion, tools and learning into one portable unit.

| System | What it is | Useful idea to borrow | Why it is not the answer |
| --- | --- | --- | --- |
| [RoboEarth action recipes](https://ai.uni-bremen.de/papers/tenorth12roboearth.pdf) | Shared web database of task recipes, object models and maps, written in OWL on the KnowRob knowledge base | Recipes list abstract steps; each robot breaks them down until it reaches motions it has. A robot self-description is matched against what the recipe needs | Heavy ontology stack, no motion data, project ended around 2014 |
| Behavior trees ([BehaviorTree.CPP](https://discourse.openrobotics.org/t/introducing-behaviortrees-cpp-who-needs-finite-state-machines-anymore/6899), [py_trees](https://py-trees.readthedocs.io/en/devel/_modules/py_trees/parsers/behaviour_tree_xml.html)) | XML trees of sequences, fallbacks and conditions, widely used in ROS 2 | Clear structure for steps, retries and recovery; subtrees give nesting | Leaves call robot-specific code, so a tree is not portable on its own |
| PDDL planning languages | Text language for actions with preconditions and effects | Preconditions and effects let a planner chain skills | Symbolic only, nothing about how to move |
| [Industrie 4.0 capability and skill model](https://arxiv.org/pdf/2209.09632) | Factory standard: a capability is what can be done, a skill is its executable version, with a fixed state machine (OPC UA, AAS) | Separate the portable "what" from the robot-specific "how"; standard skill states | Aimed at factory machines, not humanoids |
| [IEEE 1872.2 (2021)](https://sagroups.ieee.org/1872-2/) | Ontology standard for autonomous robots | Shared vocabulary for tasks and capabilities | Vocabulary, not a packet format |
| [Open X-Embodiment / RLDS](https://roboticscenter.ai/en/blog/open-x-embodiment) and [LeRobot datasets](https://huggingface.co/docs/lerobot/lerobot-dataset-v3) | Large shared recordings of robots doing tasks, used to train AI policies | Proves skills can transfer between robot bodies via learned models | Gigabytes of raw data, not compact, not readable |
| [ISO/WD 26264-1](https://arxiv.org/html/2606.19769) | Draft ISO standard for humanoid robot datasets (TC 299/WG 16, June 2026) | Metadata, provenance and versioning rules we should align with | Covers data, not skills; early draft |
| Robot descriptions (URDF, SDF, MJCF) | Files describing a robot's body or a simulated world | Use as-is to describe the robot and objects in simulation | Describe bodies, not tasks |

## Ways to store a skill

No single option wins. Readable formats are easy to share but bulky. Binary is compact but opaque. Maths is tiny but only covers movement. That points to a mix. Sizes below are rough estimates, not measurements.

| Option | Typical size of one skill | Readable by people | Works in any language | Covers movement | Fits per-robot learning |
| --- | --- | --- | --- | --- | --- |
| New small skill language (own grammar) | A few KB of text | Yes, best | Needs a parser per language | Calls motions, does not hold them | Weak |
| JSON or YAML with a schema | 5 to 20 KB | Yes | Yes, every language has a reader | Only as long number lists | Medium |
| Binary: CBOR, Protobuf or FlatBuffers | 1 to 5 KB | No, needs a tool | Yes, generated readers | Yes, compact numbers | Medium |
| Motion as maths: movement primitives ([DMPs](https://hcr.ijs.si/resources/papers/tro10.pdf), [ProMPs](https://www.ias.informatik.tu-darmstadt.de/uploads/Team/AlexandrosParaschos/promps_auro.pdf)), splines | About 25 numbers per joint, under 1 KB per motion | No | Yes | Yes, and adapts to new start and goal points | Strong: refine the numbers from practice |
| Learned model (neural policy) | MB to GB | No | Needs an AI runtime | Yes | Strong, but tied to one body type |

**What "maths storage" buys us.** A movement primitive stores a motion as a small set of weights on smooth curves. The robot replays it toward any new goal, such as a bottle in a different place, and can fine-tune the weights after each attempt. That makes it the natural home for "the robot keeps learning the skill".

## Decisions taken after this survey (2026-10-27)

- A new small grammar for the text form, with YAML accepted as an alternative.
- Robot capability list based on RoboEarth's robot self-description (SRDL).
- Shared action vocabulary and top-level class codes based on VDI 2860.
- Licence: Apache 2.0 for the spec and tools; CC BY 4.0 by default for library skills.

## Sources

- [The RoboEarth language](https://ai.uni-bremen.de/papers/tenorth12roboearth.pdf), Tenorth et al.
- [Data Standards for Humanoid Robotics](https://arxiv.org/html/2606.19769), Liu et al., June 2026 (covers ISO/WD 26264-1)
- [Capability, skill and service reference model](https://arxiv.org/pdf/2209.09632), Köcher et al., 2022
- [IEEE P1872.2 working group](https://sagroups.ieee.org/1872-2/)
- [LeRobot dataset v3 docs](https://huggingface.co/docs/lerobot/lerobot-dataset-v3)
- [Open X-Embodiment overview](https://roboticscenter.ai/en/blog/open-x-embodiment)
- [DMP paper, Ude et al.](https://hcr.ijs.si/resources/papers/tro10.pdf) and [ProMP paper, Paraschos et al.](https://www.ias.informatik.tu-darmstadt.de/uploads/Team/AlexandrosParaschos/promps_auro.pdf)
