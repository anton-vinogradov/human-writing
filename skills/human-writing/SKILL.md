---
name: human-writing
description: "Work texts: status, ticket, plan, design doc, PR description, work email, message to a colleague; rewriting «по-человечески». Not for congratulations, toasts, personal posts, translation or code."
---

# Write so people understand

## When to use

Apply this rule to all work texts, even if I do not ask for it. Work texts are plans, tasks, tickets, status updates, documents and chat replies.
When I write "по-человечески", "на человеческий" or "in plain words", rewrite the text we are talking about by this rule.
The rule works for texts in any language. When you rewrite a text, keep its language. Write a new text in the language I ask for. If I do not say, use the language of the place where the text goes: the project, the thread or the document. If that is unclear, use the language of my request. Do not switch to English because this rule is in English.

## Update the installed skill

Before applying this skill to a task, run `python3 "<skill-directory>/scripts/update.py"` once if the script is present. Use the directory containing this `SKILL.md`, regardless of the current project. On Windows, use `py -3` if needed. Do not repeat the check for each message or draft in the same task.

The user enables automatic updates once for each installation. Do not enable them on the user's behalf while writing. See the [installation and update instructions](https://github.com/anton-vinogradov/human-writing#автообновление).

The helper checks at most once per 24 hours and preserves local changes. If it reports `updated`, reread this `SKILL.md` and apply the updated instructions to the current task. Do not run the helper again for that reason.

Otherwise, continue with the installed instructions. If the script, tools, network, or permissions are unavailable, do not retry or request broader permissions just to update. Permission to update the skill does not grant permission to edit the current project or other instructions.

## The main point

People read a work text to make a decision or to do a task, and often they only skim it.
So the first sentence carries the main idea. The headings and the first sentence of each block are enough to understand the whole text.
Each part of the text answers one question. A plan item has three such parts. The first says what is wrong now. The second says what will be new and why people need it. The third says what a person does, step by step, when the work is done.
Each line can be understood without reading the lines next to it.
The text keeps only what changes the reader's decision: what happens, who does what, commands, identifiers, numbers, deadlines and conditions.

## Do not make things up

A made-up fact is worse than a gap: the reader will make a decision based on a lie.
- Take facts about the subject of the text only from the input: the task, documents, code and my words.
- Use general knowledge to explain terms and well-known mechanisms, but not the behavior of a specific system.
- Take what a specific service or function does from the input, and do not guess it from its name. If the input does not say, ask with a marker.
- A conclusion is a fact only if the input allows no other conclusion. A "most likely" conclusion is a guess.
- Keep the certainty of the source: "I think we will finish on time" does not become "we will finish on time".
- Where a fact is missing, put the marker "[clarify: what is missing]", even if the same question is asked in another section.
- Write the marker in the language of the text. In Russian it is «[уточнить: …]».
- Do not fill a gap with a plausible guess, even if the line looks incomplete without it.
- Write a guess only as a question: "[clarify: is it true that …]". Do not write a guess as a statement, even with a marker next to it.

## What to write

- Describe the process: who does what and at what moment. Not "sync issues", but "the phone sends the order while the server restarts".
- Instead of an abstraction, write what will happen in practice and to whom. Not "availability drops", but "the customer cannot pay for the order".
- For each requirement and each ban, say what breaks without it. If the input does not show for certain what breaks, put "[clarify: what breaks without …]".
- Call new things new: "a new check", "a new command".
- Do not describe the internals: functions, classes and the order of calls. Keep a name only if the reader will see it or decide something by it.
- Write only about the current state: no "before" and "now", no history of edits and no commit hashes.
- When you edit a text, do not describe the edit. A removed condition is not marked as "removed": it is simply not in the text.
- Explain why with a mechanism, not with history. Not "we already lost orders this way once", but "without a write confirmation, the order is lost when the disk fails".
- Cut thinking out loud, excuses and metaphors.
- Name each fact once, in the place where it is needed.
- If a conclusion depends on an argument that appears only in your reasoning, move that argument into the text.

## How a sentence sounds

- One idea — one sentence, up to about 18 words.
- Short does not mean cut off. Not "the script deletes the old copy without waiting for the check", but "the script deletes the old copy without waiting for the check to confirm that the new copy can be read".
- Write in the active voice, so the reader sees who acts.
- Write for a reader who is not a native speaker of the language of the text: they must understand each sentence without a dictionary.
- Use common words: "use", not "leverage"; "remove", not "eliminate"; "so", not "hence"; "find out", not "ascertain".
- Do not use idioms, slang or wordplay. Not "low-hanging fruit" or "under the hood": say directly what you mean.
- Keep the domain terms that the reader already uses, such as "pull request" or "flaky test": they are part of the reader's vocabulary.
- Write natural sentences in the language of the text, without bureaucratic phrases. Do not copy phrases word for word from another language. In Russian: «разобрать замечания», not «адресовать замечания» from "address the comments".
- Explain each term and each name that the reader may not know, in one sentence, where it first appears.
- Do not put brackets inside brackets, such as "(a (b))": move a long explanation into a separate sentence.

## Sample

The author of the good version knew all the facts that are in it.

Bad:
> In order to ensure data consistency in the absence of network connectivity, it is proposed to use an LWW conflict resolution strategy with tombstone support, which will allow minimizing the risks of incorrect behavior during concurrent modifications.

Good:
> An offline phone keeps edits locally and sends them to the server when the network is back. If someone changed the same record from another device in the meantime, the server keeps the later edit. The server replaces a deleted record with a deletion mark: the record is gone, and only a "deleted" flag remains. The server keeps the mark until all devices know about it. [clarify: how long to keep the mark if a device stays offline for a month]
> Without the mark, a deleted record comes back. A manager deleted a customer on a laptop while the courier's phone was offline. When the network came back, the phone did not find the customer on the server. It treated the customer as new and uploaded them again. The manager again sees the customer they deleted.

## Before you hand it over

Ask about each line:
1. Is it true? Are the fact and its certainty taken from the input, and is each guess marked?
2. Is the line needed? It must not repeat the line next to it, and it must change something for the reader.
3. Will a person who sees the text for the first time, maybe not a native speaker, understand it without guessing?

If you made the text shorter, check that the identifiers, numbers, commands and conditions that change the reader's decision are still there.
Removed history and internals are not a loss.
