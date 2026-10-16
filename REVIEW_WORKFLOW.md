# Conversational review workflow — working specification

These are the user's preferences agreed during the Spanish demo. This document
is the source for a future Codex skill; it is not yet an installed skill.
Update it as we learn from live reviews. The MCP server supplies operations;
the reviewing agent must actually call them and check their results.

## Current demo override: batches of ten

The user subsequently requested ten-card batches to reduce terminal approvals.
This overrides the immediate-per-card-save rule below for this demo:

- Prepare up to ten cards in one MCP call; the agent receives both sides, but
  presents only each prompt until the user has attempted it. These are queued
  practice previews, not saved reviews. Anki may return fewer than ten.
- During conversation, acknowledge answers immediately and keep a pending list
  of card IDs and ratings. Apply explicit ratings or the authorized Good default.
- Do not run tools between every spoken answer. Move through the prepared list
  directly, pausing for disputed answers as agreed. Never invent another card.
- At ten completed cards, or when the user requests a save/end, submit the staged
  ratings together and check each receipt. Partial saves are possible; report
  them accurately and never resubmit already saved or uncertain reviews.
- Say "pending" before the batch is saved, and confirm "saved" only after the
  batch result. A session loss can lose the conversational pending list; do not
  claim it is durably stored. On reconnect, reconcile before replaying anything.
- This is a latency workaround for the terminal-mediated demo. The eventual
  direct MCP workflow can return to saving each card immediately without the
  approval overhead. Batch preview can change review ordering and recorded timing;
  it is not a validated production replacement for live Anki scheduling.

## Session policy

- Review hands-free where possible, with short prompts and minimal narration.
- Acknowledge the user's answer immediately, before waiting for terminal/tool
  operations, so the user knows they were heard. For an unambiguous familiar
  answer, brief correctness feedback can be immediate; if uncertain, say "I heard
  you—checking" and verify against the back before judging. Do not say "saved"
  until the receipt confirms it. Tool latency must not create unexplained silence.
- Fast progression is a core requirement: avoid unnecessary silence, repeated
  direction/rating questions, and operational chatter between cards. After a
  completed answer, perform reveal, save, receipt check, and fetch promptly.
  Terminal approvals and extra tool round trips currently limit the demo; direct
  agent-to-MCP integration and measured end-to-end latency are required next.
  Never achieve speed by skipping persistence checks or advancing before saving.
- Present the card prompt alone when the translation direction is understood.
  For example, say **hola**, without adding "What is that in English?"
- Announce the session's language/direction convention once. For a mixed-language
  deck, identify the language whenever the intended answer would be ambiguous,
  particularly English-to-target-language cards: **Spanish: house**.
- Use note/deck metadata and explicit user mappings to choose language/direction.
  Do not guess which language an ambiguous prompt expects. If unknown, clarify.
  The current demo has Spanish on Front and English on Back; Basic/reversed
  card ordinal 0 prompts Spanish and ordinal 1 prompts English. The tools do not
  yet return language/direction metadata; add it before mixed-deck use.
- **The user authorizes Good as the default rating for a completed card when
  they do not specify another rating.** Explicit Again, Hard, Good, or Easy wins.
  Do not infer Easy from a correct answer or Again from an incorrect answer.
  Do not apply this user's default to other users without their authorization.
- The agent still sends an explicit rating value to MCP. There is no implicit
  rating triggered merely by fetching, revealing, speaking, or disconnecting.
- The agent judges correctness against the revealed back, allowing reasonable
  synonyms. Correctness feedback and the Anki rating are separate: a correct
  answer does not require asking for a rating; the authorized Good default applies.
- **Spanish → English:** for a correct answer, say "Correct" and continue after
  saving. Do not routinely read the English back aloud.
- **English → Spanish:** always pronounce the Spanish answer from the back,
  even when the user answered correctly, so the user hears a pronunciation model.
  Use natural Spanish pronunciation in voice mode. Showing text alone is not an
  audio feature of the MCP server; speech is supplied by the conversational client.
- If the agent judges an answer incorrect or ambiguous, briefly explain the
  discrepancy and pause for the user's response or debate before saving or
  advancing. Do not automatically mark Again or commit Good during a dispute.
  Resolve the accepted answer and any rating override, then apply the agreed
  default if no override is given. The user can correct the agent's judgment.

## One-card loop

1. Fetch the next card through MCP. Remember its card ID and review token.
2. Present just its question, with a language cue when needed. Wait for the
   user's answer; never answer on their behalf or expose the back early.
3. Let the user finish their utterance, including an appended rating such as
   "hello, easy". Never commit partway through a streamed transcript.
4. Reveal the answer through MCP internally and judge the user's attempt.
   Revealing to the agent does not require reading the entire back to the user.
   Allow reasonable translation synonyms; use the direction-specific speech
   rules above. If incorrect/ambiguous, explain and pause for discussion before
   committing. Never claim the agent's own knowledge is the saved back.
5. At the end of discussion of that card, use the explicit rating, or Good if
   none was supplied. Do not ask the four-way rating question on every card.
   A question, "wait", "let me think", or continued discussion keeps the card
   open; silence/disconnection is not a completed answer or rating.
6. Immediately call `rate_card` with that token and rating. This must happen
   **before** fetching or presenting another card. Confirm `recorded: true` and
   `service_available: true`. A verbal "correct" or "next" is not a tool call.
7. Continue to the next card after confirmation. For transparency during the
   demo, a short "Correct" is sufficient for a correct Spanish-to-English answer.
   Do not routinely ask "Rating?"; the authorized default is Good. If the user
   switches to discussing the project,
   finish saving the completed review, then pause the loop.

Example:

> Agent: hola  
> User: Hello, easy.  
> Agent internally: reveal → rate Easy → check saved receipt → next card.  
> Agent: Easy. Adiós.  
> User: Goodbye.  
> Agent internally: reveal → rate Good (authorized default) → check → next.

If the back is Spanish, speak that Spanish answer as part of feedback. If a
translation seems wrong, keep the current card open for discussion instead of
running the rate/next steps immediately.

## Pauses, retries and failures

- Keep the current card open while discussing it. An explicit skip/cancel uses
  `cancel_review`, which records no review. A pause alone does not assign a rating.
- A same-token/same-rating retry can retrieve the cached receipt in the live
  process. Do not submit a fresh token for a possibly completed review.
- If `recorded` is null or the status is uncertain, stop. Tell the user the save
  is uncertain and inspect history before continuing. Never guess success.
- If a receipt says recorded but the service is unavailable, the review is saved;
  stop and recover the service rather than repeating the review.
- After a disconnect/restart, verify stored history and current state. Do not
  automatically replay verbal answers or assume a previous "next" was saved.
  Old review tokens are not valid in a new server process.
- Changing the rating after a confirmed save requires a future supported undo/
  correction workflow. Do not create another review to overwrite a receipt.
- Anki can legitimately show a card again soon, depending on its rating and
  learning schedule. A repeat alone is not proof that a review was lost.

## Demo checkpoint

The first live **hola → hello** review was explicitly rated **Easy** and saved
through MCP. Earlier voice-only acknowledgments had not saved any reviews.
Do not retrospectively submit those other answers without checking with the user.

## Acceptance checks for the future skill

- "hello, easy" produces one Easy write before the next question.
- "goodbye" at the end of card discussion produces one Good write, without a
  rating prompt, using this user's authorized session policy.
- An appended Hard/Again overrides the default; an unfinished answer does not save.
- Mixed-language English prompts include the target language. A fixed Spanish
  session avoids repetitive translation-direction questions.
- Discussion/pause/cancel and storage-error paths never advance unsafely.
- Receipts, not conversational acknowledgments, determine what was recorded.
- A correct Spanish-to-English answer gets brief correctness feedback without
  repeating the English back; English-to-Spanish always includes the Spanish back.
- An incorrect-answer judgment gives the user a chance to debate before saving.

These are agent workflow acceptance criteria, not claims that conversational
behavior is enforced by the current server's pytest suite. Test a future skill
against scripted conversations and recorded tool calls as well as service tests.
