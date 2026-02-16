# Scrimmage Planning

This file contains instructions for the Scrimmage Master on how to run a Scrimmage Planning meeting.

## Purpose of the meeting

A Scrimmage Planning meeting exists to check that items into the backlog are ready for implementation, and break them down into smaller, more specific items where needed.

## Inputs

Could be existing items in the backlog database, could be directly from the user saying "we want to implement this".

## Outputs (deliverables)

A set of items in the backlog database that are ready for the team to start working on them - meaning they are appropriately sized and scoped and any ambiguity in what they're asking for has been refined with the user.

**Appropriately sized** means that implementing the item will fit inside the context window for a single agent.

## Roles

* The Scrimmage Master is facilitator for the meeting. They spawn the participants, brief them, manage the conversation, and record the results in the backlog database (via `backlog_db.py` — see `scrimmage/scrimmage-team.md` § Product Backlog for the API). They also interact with the user to get them to refine requirements, if this is needed.

* Between two and five other agents in specific roles are also in the meeting. They each represent their own specialist area, although they also each bear in mind the need to reach a sensible outcome for the project overall.

* All meeting participants (including the Product Owner and specialist agents) should be spawned with **model: opus**, since planning requires architectural reasoning and cross-cutting judgement.

## Stages

1. The user asks the SM to run a Scrimmage Planning meeting. The user provides either backlog item numbers or a free-text description of what they need the team to implement.

2. The SM thinks about what information their teammates are going to need at the start of the meeting. Where the input is one or more backlog items, this will definitely include a description of those items. It's more credit-efficient for the SM to provide this info to all meeting participants than for each participant to get it for themselves. There might be other info participants will need as well, if so the SM should get it ready for them.

3. The SM thinks about what role teammates should be in the meeting. The SM themselves will be in the meeting, and so will the Product Owner. An additional between 1 and 4 agents must be in the meeting, with roles appropriate to the items that will be discussed (roles as listed in scrimmage-team.md, "Team Structure").

4. The SM spawns the agents needed for the meeting, as teammates so they have a tmux window each, not as subagents (the user wants to be able to see each tmux window). The SM refers them to this file for info and provides the briefing info they have already compiled.

5. **Hub-and-spoke discussion.** The SM acts as facilitator and message hub. Participants send their input to the SM via direct message. The SM synthesizes the inputs and relays summaries and questions back to participants (also via direct message). This avoids the cost of broadcasting every remark to every participant. The SM should ensure each participant's perspective is represented fairly in the summaries.

6. During the meeting, no participant may spawn subagents or start background tasks. These would effectively take the participant out of the meeting (consuming their context and attention), and their perspective might be overlooked.

7. Participants either come to agreement on a recommended approach (in which case the SM creates/modifies backlog items via `backlog_db.py`) or ask the user for further info (eg if the spec is not clear), or provide the user with a choice of options (telling the user about the pros and cons or trade-offs inherent in each one).

8. **Consensus limit.** If the group has not reached consensus within 10 turns of discussion, the SM stops the discussion, selects the top two options, and presents them to the user with an explanation of the trade-offs. The user decides.

9. **Dependency mapping.** Once items are agreed, the group explicitly identifies ordering constraints — which items depend on other items being completed first. The SM records these dependencies in the backlog. This feeds directly into the spawn-on-merge workflow (see `scrimmage/notes/scrimmage-master.md` § Spawning Checklist).

10. When an approach has been agreed and the backlog items created, the SM spawns (as a teammate agent in a tmux window) Pierre peer reviewer who checks the items and gives feedback to the group.

11. The group addresses Pierre's feedback and improves the items as needed. If changes are made, return to step 10 and give Pierre another chance to review.

12. The SM shuts down the other agents which have been involved in the scrimmage planning meeting.
