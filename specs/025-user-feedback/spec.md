# Feature Specification: In-App User Feedback

**Feature Branch**: `025-user-feedback`  
**Created**: 2026-11-18  
**Status**: Draft  
**Input**: User description: "In-app user feedback for ProcurePilot. Any workspace member (owner, buyer, branch_manager, approver, viewer) can submit feedback from a persistent widget in the web app shell: text (required), up to 5 screenshots, and one optional audio. Context is captured by the system, not trusted from the client. Members see their own submissions; the workspace owner gets a read-only inbox of the workspace's feedback; no workspace role can change status, label or delete. The ProcurePilot team triages across workspaces through a separate platform-operator path. Out of scope for v1: video, threaded replies, mobile app, anonymous feedback. Reference: FormCraft feedback specs 011, 013, 014."

## Clarifications

### Session 2026-11-18

- Q: Can a submitter withdraw their own feedback? → A: Yes, but only while its status is "new"; once it is "reviewed" or "resolved" it can no longer be withdrawn.
- Q: Should submitters pick a feedback category? → A: Optionally, one of Bug, Idea, Question or Other (default none); operators still add their own labels separately.
- Q: How should the ProcurePilot team learn of new feedback? → A: Through the triage view as the primary channel, plus an optional daily email digest each operator can turn on for themselves; no immediate per-submission alerts.
- Q: What submitter identity do operators see? → A: The submitter's name and email, plus workspace and role.
- Q: How can members add screenshots? → A: By uploading image files from the device or pasting an image from the clipboard; no one-click page capture in v1.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit text feedback from anywhere (Priority: P1)

A workspace member hits a problem or has an idea while working. From any page, they open a persistent feedback control, type a message, and send it. They see a confirmation, and the feedback is recorded with the page they were on, the app version, their language and their role, all filled in by the system.

**Why this priority**: Text is the baseline channel and the whole point of the pilots: it gets real user reactions to the ProcurePilot team. Nothing else has value without it.

**Independent Test**: Sign in as any role, open the feedback control, send a message, and confirm it appears in the sender's own list with status "new" and the correct captured context.

**Acceptance Scenarios**:

1. **Given** a signed-in member of any role on any page, **When** they open the feedback control, enter a message and send, **Then** the feedback is saved, a success confirmation is shown, and it appears in their own submissions with status "new".
2. **Given** a member composing feedback, **When** the message is empty or only whitespace, **Then** sending is blocked and a validation message is shown.
3. **Given** a member composing feedback, **When** the message reaches 2000 characters, **Then** no further characters are accepted and the remaining count reads 0.
4. **Given** a member who just sent feedback, **When** they try to send again within 30 seconds, **Then** the second send is refused with a clear message showing the time left, and their draft is kept.
5. **Given** a submission, **When** it is stored, **Then** the page address, app version, language, member role and demo-workspace flag recorded come from the system, and any values the client supplied for these are ignored.
6. **Given** a member with the Arabic language selected, **When** they open the feedback control, **Then** all text appears in Arabic and the layout is right-to-left.
7. **Given** the feedback control is open, **When** the member reads it, **Then** a notice states that ProcurePilot staff can see their feedback, screenshots, name and email.
8. **Given** a member composing feedback, **When** they send without choosing a category, **Then** the feedback is accepted with no category; **When** they choose one of Bug, Idea, Question or Other, **Then** that category is saved and shown with the submission in every view.

---

### User Story 2 - Attach screenshots (Priority: P2)

A member wants to show what they see. While writing feedback they attach up to five screenshots, preview thumbnails, remove any they don't want, and send.

**Why this priority**: Screenshots make reports actionable, but text alone (P1) already delivers a usable channel.

**Independent Test**: Send feedback with several screenshots and confirm they are stored with it and visible to the sender, and that invalid files are rejected before any upload.

**Acceptance Scenarios**:

1. **Given** a member composing feedback, **When** they attach JPEG, PNG or WEBP images of up to 5 MB each, **Then** thumbnails appear and the images are saved with the submission.
2. **Given** a member who has attached 5 screenshots, **When** they try to add a sixth, **Then** it is refused with a clear message.
2a. **Given** a member with an image on their clipboard, **When** they paste into the feedback form, **Then** it is added as a screenshot with a preview; **When** the clipboard holds no image or a disallowed type, **Then** nothing is added and a clear message is shown.
3. **Given** a member composing feedback, **When** they select a file that is too large or not a supported image type, **Then** it is rejected immediately, before any upload, with a message naming the reason.
4. **Given** a member with attached screenshots, **When** they remove one, **Then** it is not included in what is sent.
5. **Given** an upload that fails during sending, **When** it still fails after one retry, **Then** sending is blocked, nothing is partially saved, and the member can remove the attachment and send the text alone.

---

### User Story 3 - Attach a voice message (Priority: P3)

A member who prefers speaking records a voice message of up to two minutes in the browser, or uploads an audio file, previews it, and sends it with the text.

**Why this priority**: It lowers the effort for people who dislike typing, but the feature works fully without it.

**Independent Test**: Record or upload audio, play it back before sending, send, and confirm the sender can play it from their own list.

**Acceptance Scenarios**:

1. **Given** a member composing feedback, **When** they record audio and stop, **Then** a playback control appears and they can re-record or discard it.
2. **Given** a recording in progress, **When** it reaches 2 minutes, **Then** it stops automatically and the member is told.
3. **Given** a member composing feedback, **When** they upload an MP3, M4A, WAV or WebM file of up to 10 MB, **Then** it is accepted as the audio attachment; larger or other types are rejected before upload.
4. **Given** a browser that cannot record, or microphone permission denied, **When** the feedback control opens, **Then** the record option is hidden or disabled with an explanation, and text, screenshots and file upload still work.
5. **Given** a submission, **When** it is sent, **Then** it carries at most one audio attachment.

---

### User Story 4 - Follow my own feedback, and the owner's workspace inbox (Priority: P4)

Every member can open a list of feedback they have sent, with its current status (new, reviewed, resolved). The workspace owner can additionally open a read-only inbox of all feedback sent by members of their workspace, so they can see whether their team's issues are being heard.

**Why this priority**: It closes the loop for submitters and gives owners visibility, but collection (P1–P3) and team triage (P5) matter first.

**Independent Test**: As two members of one workspace, send feedback; confirm each sees only their own, the owner sees both read-only, and a member of another workspace sees neither.

**Acceptance Scenarios**:

1. **Given** a member who has sent feedback, **When** they open their feedback list, **Then** they see only their own submissions, with text, attachments and status.
2. **Given** a workspace owner, **When** they open the workspace inbox, **Then** they see all feedback sent by members of that workspace and nothing from any other workspace.
3. **Given** the owner's inbox, **When** the owner looks for a way to change status, label or delete, **Then** none is offered, and an attempt through any other route is refused.
4. **Given** a buyer, branch manager, approver or viewer, **When** they try to open the workspace inbox, **Then** it is not shown and direct access is refused.
5. **Given** a member of workspace A, **When** they request a submission that belongs to workspace B, **Then** the response is "not found", never "forbidden".
6. **Given** a member's own submission with status "new", **When** they withdraw it and confirm, **Then** the text and attachments disappear from their list, the owner's inbox and the triage view, and the stored files are deleted.
7. **Given** a member's own submission with status "reviewed" or "resolved", **When** they look for a way to withdraw it, **Then** none is offered, and an attempt through any other route is refused.
8. **Given** a member who is not the submitter (including the owner), **When** they try to withdraw someone else's submission, **Then** the response is "not found".

---

### User Story 5 - ProcurePilot team triages feedback across workspaces (Priority: P5)

A ProcurePilot team member with platform-operator access reviews feedback from all workspaces in one place, filters by status and workspace, plays audio and views screenshots, and moves each item through new, reviewed and resolved and can label it.

**Why this priority**: It is how the feedback becomes action, but it needs submissions to exist first. It is the highest-risk story because it deliberately crosses workspace boundaries, so it is specified narrowly.

**Independent Test**: With operator access, view feedback from two workspaces, change a status and add a label, and confirm the change is recorded; with a normal workspace owner, confirm none of this is possible.

**Acceptance Scenarios**:

1. **Given** a platform operator, **When** they open the triage view, **Then** they see feedback from all workspaces with workspace, submitter name and email, submitter role, page, text, category, status and labels, and can filter by status, workspace and category.
2. **Given** a platform operator, **When** they change an item's status among new, reviewed and resolved, or edit its labels, **Then** the change is saved and the submitter and the owner see the new status.
3. **Given** a platform operator, **When** they open a submission's screenshots or audio, **Then** access works through short-lived links that stop working after a short time.
4. **Given** a platform operator, **When** they try to read or change anything other than feedback, **Then** the operator access grants nothing.
5. **Given** any workspace role (including owner), **When** they try to reach the triage view or change status or labels, **Then** access is refused.
6. **Given** a feedback submission, an operator viewing it, or an operator changing its status, **When** the action happens, **Then** an audit record of who, what and when is written and cannot be altered or removed.
7. **Given** a platform operator who has turned the daily digest on, **When** new feedback arrived since the last digest, **Then** they receive one email that day listing, per item, the workspace, category and a short excerpt, with a link to the triage view; **When** nothing new arrived, **Then** no email is sent.
8. **Given** a platform operator who has not turned the digest on, **When** new feedback arrives, **Then** they receive no email and still see the item in the triage view.

---

### Edge Cases

- Feedback is sent while offline or the connection drops mid-send: the member sees an error, the draft and attachments stay in the form, and nothing is silently lost or half-saved.
- A member double-clicks Send: only one submission is created.
- The member's session expires while composing: they are asked to sign in again, and the draft is not discarded before that.
- A screenshot contains a colleague's data: it is visible only to the sender, the owner of that workspace, and platform operators, which is why the notice is shown.
- A member is removed from the workspace after sending: their earlier feedback remains visible to the owner and operators; the member can no longer access it.
- A file is renamed to look like an image or audio file: the type is verified from its content, not its name.
- The member's screen is 360 px wide: the control, previews and lists remain usable without horizontal scrolling.
- An operator's access is withdrawn: they lose all access to feedback immediately.
- A submitter withdraws a submission at the moment an operator is changing its status: whichever change is saved first wins; if the status has already moved past "new", the withdrawal is refused and the submitter is told why.
- A workspace is a demo workspace: its feedback is flagged so triage can separate pilot input from demo traffic.

## Requirements *(mandatory)*

### Functional Requirements

**Submitting**

- **FR-001**: The system MUST offer a persistent feedback control on every page of the signed-in web app to members of every workspace role (owner, buyer, branch manager, approver, viewer).
- **FR-002**: The system MUST require a non-empty text message of up to 2000 characters for every submission.
- **FR-002a**: The system MUST let the submitter optionally choose one category (Bug, Idea, Question or Other) per submission, default none, and MUST NOT require it to send.
- **FR-003**: The system MUST allow up to 5 screenshots per submission (JPEG, PNG or WEBP, up to 5 MB each), added either by choosing or dropping image files from the device or by pasting an image from the clipboard, and show a preview of each before sending. Pasted images follow the same type, size and count rules as uploaded files.
- **FR-004**: The system MUST allow one optional audio attachment per submission, either recorded in the browser (up to 2 minutes) or uploaded (MP3, M4A, WAV or WebM, up to 10 MB), with playback before sending.
- **FR-005**: The system MUST validate file type (from content), size and count before any upload and reject invalid files with a message naming the reason.
- **FR-006**: The system MUST hide or disable recording where the browser or permissions do not support it, leaving all other inputs usable.
- **FR-007**: The system MUST refuse a second submission from the same member within 30 seconds, keep their draft, and say how long to wait.
- **FR-008**: The system MUST treat a submission as all-or-nothing: if text or any attachment cannot be saved, nothing is stored and the member keeps their draft; a repeated send of the same submission MUST NOT create duplicates.
- **FR-009**: The system MUST record, for each submission, the workspace, the submitter, the submission time, and the page address, app version, language, member role and demo-workspace flag, all set by the system from the verified session and request; client-supplied values for these MUST be ignored.
- **FR-010**: The system MUST show a success confirmation after saving, and the notice that ProcurePilot staff can see feedback, screenshots and the submitter's name and email whenever the feedback control is open.
- **FR-011**: The system MUST show every user-facing string in English or Arabic according to the member's language, with right-to-left layout for Arabic, and the control MUST be usable from 360 px width upward.

**Visibility and permissions**

- **FR-012**: Every member MUST be able to list and open their own submissions, with attachments and current status, and MUST NOT see anyone else's.
- **FR-013**: The workspace owner MUST additionally have a read-only inbox of all submissions from members of their own workspace, and no other workspace role MAY access it.
- **FR-014**: No workspace role, including owner, MAY change a submission's status or labels or delete a submission or attachment, with one exception: a submitter MAY withdraw their own submission while its status is "new". Withdrawal removes the text and all attachments from every view (the submitter's, the owner's and the operators') and deletes the stored files; once the status is "reviewed" or "resolved", withdrawal is refused.
- **FR-015**: A request for a submission or attachment in another workspace MUST behave as "not found", never "forbidden".
- **FR-016**: Feedback and attachments MUST be isolated per workspace at the data layer, not only in the application, and attachments MUST NOT be reachable by any permanent public address.

**Platform-operator triage**

- **FR-017**: The system MUST provide a separate platform-operator access path, identified by a dedicated verified credential and not by any workspace role, that lets the ProcurePilot team list and open feedback across all workspaces, filter by status, workspace and category, and view attachments.
- **FR-017a**: The triage view MUST show each submission's submitter name and email, workspace and member role to platform operators; the daily digest (FR-024) MUST NOT include the email address.
- **FR-018**: A platform operator MUST be able to set status (new, reviewed, resolved) and edit labels, and MUST NOT be able to read or change anything outside feedback through that access.
- **FR-019**: Attachment access for operators and members MUST use links that expire within a short time and are issued only after an access check.
- **FR-020**: The system MUST write an audit record when feedback is submitted, when an operator views a submission, when an operator changes status or labels, and when a submitter withdraws a submission (recording who, when and the submission identifier, but not the withdrawn content); audit records MUST be append-only.
- **FR-021**: Withdrawing a platform operator's access MUST take effect on their next request.
- **FR-024**: The triage view MUST be the primary way the team sees new feedback, and each platform operator MUST be able to turn a daily email digest on or off for themselves (default off). The digest MUST contain only the workspace, category and a short excerpt per item plus a link to the triage view, never attachments, and MUST NOT be sent on days with no new feedback. Immediate per-submission alerts are not provided.
- **FR-022**: The system MUST NOT take any purchasing or other business action as a result of feedback; feedback is informational only.

**Retention**

- **FR-023**: The system MUST delete or anonymise feedback and its attachments 12 months after submission, regardless of status.

### Key Entities

- **Feedback submission**: One piece of feedback. Holds workspace, submitter, submission time, message text, optional submitter category (Bug, Idea, Question, Other), status (new, reviewed, resolved), operator labels, and system-captured context (page address, app version, language, member role, demo-workspace flag). Belongs to exactly one workspace.
- **Feedback attachment**: A screenshot (up to 5) or one audio file linked to a submission. Stored privately within its workspace; never publicly addressable.
- **Feedback label**: A short tag the ProcurePilot team applies during triage.
- **Platform operator**: A ProcurePilot team member with a dedicated access credential, distinct from any workspace membership, limited to feedback triage, with a personal on/off setting for the daily digest.
- **Audit record**: Append-only entry of who did what to which submission and when.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A member can open the feedback control, write a message and send it in under 60 seconds.
- **SC-002**: 100% of invalid files (wrong type, too large, too many) are rejected before any upload, with a stated reason.
- **SC-003**: Zero submissions are lost or duplicated after the member has seen the success confirmation, including after a dropped connection and a retry.
- **SC-004**: In isolation testing across at least two workspaces, 0 submissions or attachments from one workspace are readable by members, owners or links of another, and every such attempt returns "not found".
- **SC-005**: 100% of attempts by non-owner members to open the workspace inbox, and by any workspace role to change status or labels, are refused.
- **SC-006**: Every submission, operator view and operator status change has a matching audit record.
- **SC-007**: The control passes accessibility checks with zero violations in both English and Arabic, and works at 360 px width in both reading directions.
- **SC-008**: The ProcurePilot team can find and triage a new submission from any workspace in under 2 minutes, without asking the submitter for more information in at least 80% of pilot submissions that include a screenshot.

## Assumptions

- Only signed-in workspace members can submit; anonymous feedback is out of scope.
- The workspace owner's inbox is read-only in v1; owners cannot reply, relabel or delete.
- Submitters see status changes by opening their list; no email or push notification on status change in v1.
- Feedback is internal: it is visible only to the submitter, their workspace owner, and platform operators.
- Platform-operator access is granted and withdrawn by the ProcurePilot team outside the workspace member system; the mechanism is decided in planning.
- The same behaviour applies to demo workspaces, which are flagged for triage.
- The 30-second cooldown, file limits and 2-minute recording limit follow the reference implementation (FormCraft specs 011 and 013).

## Out of Scope

- Video attachments and video recording.
- One-click capture of the current page from within the feedback control.
- Threaded replies or conversations between the ProcurePilot team and submitters (a later phase; compare FormCraft spec 014).
- The Flutter mobile app (follow-up spec).
- Anonymous or signed-out feedback.
- Workspace-owner actions on feedback (status, labels, delete, reply).
- Analytics, reporting or automatic categorisation of feedback.
- Immediate (per-submission) email, push or chat alerts to the ProcurePilot team, and any notification to submitters or owners (the optional operator daily digest in FR-024 is in scope).
