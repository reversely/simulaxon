"""How the agent names what it makes: projects, experiments, comparisons (#11).

The owner (2026-11-14): "The guidelines for autotitling must be more academically oriented."

GUIDE goes into every agent's system prompt (sessions.py for chats, on Claude Code and on the planner; agent.py), and
ARG is the description of each tool's title argument, so a title looks the same whoever writes it.
"""

GUIDE = """Titles. Every project and experiment you create gets a title in the form a methods section or a paper uses:
- Lead with the paradigm or manipulation in the field's standard term, such as binocular rivalry, functional localizer,
  periodic full-field stimulation, action observation, violation of expectation, encoding-model fitting, leave-one-out
  attribution. Then the contrast and what is measured, such as "face versus object selectivity in the fusiform face area".
- Use the field's names for regions, models and datasets: fusiform face area, MT, anterior intraparietal area, TRIBE v2,
  Human Action Dataset, fLoc.
- A replication, or a study built on a published one, ends with its source in author-year form: "(Kanwisher et al.,
  1997)", or "(after Tong et al., 1998)" when the design is adapted. A variant of an earlier project names what changed
  after a colon: "Face and house rivalry: alternation rates of 1.5 to 12 s".
- State the design, never the finding. No questions, no first person, no colloquial phrasing ("a face to one eye").
- Sentence case, at most 90 characters. The project's question carries the plain-language question; the title is its
  academic name.
- Conditions and comparisons are named in plain words, as a figure legend would: "Bodies", "Objects", "Bodies against
  objects". Never identifiers such as bodies_vs_objects.

Questions. Every project's question (the heading of its page) is one grammatical sentence a paper's introduction could
end with (#24):
- State the comparison and the measure: the conditions as categories in the plural ("faces", "height-matched vases"),
  the region by its field name ("the fusiform face area", "MT", "face-selective cortex"), and that the response is
  TRIBE v2's prediction when the contrast is the point. "Do face-selective regions show a larger predicted response to
  faces than to height-matched vases?"
- A replication names its source: "... as Epstein and Kanwisher (1998) reported?"
- No first or second person, no colloquial phrasing ("what you see", "follow"), no template fill ("Does a face raise the
  face regions ..."), no identifiers. At most 160 characters; one question mark."""

QARG = ("one grammatical sentence a paper's introduction could end with, as the question guidelines in your instructions say: "
        "the conditions as plural categories, the region by its field name, the measure; a replication's source; at most 160 characters")

ARG = ("the academic name, as the title guidelines in your instructions say: the paradigm, then the contrast and the "
       "measure, a replication's source in author-year form, at most 90 characters; never a question or a finding")
