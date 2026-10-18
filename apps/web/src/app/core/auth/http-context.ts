import { HttpContextToken, HttpRequest } from '@angular/common/http';

/**
 * Lets a request rebuild itself before the interceptor replays it after a refresh. A request
 * whose BODY carries the refresh token (the workspace switch) must not be replayed verbatim:
 * the refresh just rotated that token, so the replay would spend a dead one.
 */
export const REBUILD_ON_REPLAY = new HttpContextToken<
  ((req: HttpRequest<unknown>) => HttpRequest<unknown>) | null
>(() => null);

/**
 * Opts a request outside our API into carrying the session's bearer token. Only for a target
 * our own API handed back: the quotation upload URL is a Supabase Storage object URL that
 * Storage authorises with the member's JWT (documents/service.py `_signed_upload_url`), not a
 * self-authorising presigned URL. Everything else outside the API base never sees the token.
 */
export const SEND_SESSION_TOKEN = new HttpContextToken<boolean>(() => false);
