-- Non-blocking inbox task retained until a human authorises or refuses the quotation.
alter type review_task_reason add value if not exists 'ready_to_authorise';
