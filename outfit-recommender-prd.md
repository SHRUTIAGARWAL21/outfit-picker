# Product requirements document — AI wardrobe and virtual try-on

**Status:** Draft v1
**Date:** 21 August 2026
**Document style:** ASD-STE100 Simplified Technical English

---

## 1. Summary

The product is a web application. A user uploads photos of their own clothes. The user also creates a base avatar from a full body photo. The system reads each photo with a vision model. It stores a structured description of each item.

The user then asks for an outfit in plain text. The system selects the best combinations from the user's own wardrobe. It renders an image of the user in each outfit. The user can keep the outfits they like.

The key idea is this: the system only recommends clothes that the user already owns.

---

## 2. Goals and non-goals

### 2.1 Goals

1. Let a user digitise a wardrobe with low effort.
2. Give five to ten ranked outfit suggestions for a stated need.
3. Show each suggestion as an image of the user, not as a text list.
4. Keep the liked outfits for later viewing with no new generation cost.
5. Keep the median request under 30 seconds to the first visible image.

### 2.2 Non-goals for the first release

1. No shopping. The system does not recommend items to buy.
2. No social features. Follow and following come later.
3. No mobile application. The web client must work on a phone browser.
4. No cross user search. Each wardrobe is private.

---

## 3. User roles

| Role           | Description                                                    |
| -------------- | -------------------------------------------------------------- |
| New user       | Has no avatar and no wardrobe. Must complete onboarding.       |
| Active user    | Has an avatar and at least four garments. Can request outfits. |
| Returning user | Has liked outfits saved in the interest section.               |

---

## 4. Functional requirements

### 4.1 Authentication

- The user signs up with an email address and a password.
- The system stores an Argon2id password hash. It never stores the password.
- The system creates a server side session. It stores the session in Redis.
- The session ID travels in an `httpOnly`, `Secure`, `SameSite=Lax` cookie.
- The user can log out. The logout deletes the session from Redis at once.
- Google login is post-MVP. See section 12.

### 4.2 Onboarding and the avatar

- A new user must create an avatar before the wardrobe unlocks.
- **Primary path.** The user uploads one full body photo. The photo must show the whole body. The background should be plain.
- **Fallback path.** The user does not want to upload a photo. The user then selects a body type, a height, a gender presentation and a hair type. The system generates one avatar image from these selections.
- Both paths produce the same result: one base image plus one structured profile.
- The system runs one vision call on the base image. It extracts the body shape, the proportions, the skin undertone, the hair colour and the eye colour.
- The user can view and correct the extracted values.

### 4.3 The wardrobe

- The wardrobe is the left panel of the main screen.
- A new user sees an empty state with an upload prompt.
- The user uploads one photo per garment. The garment must be flat and fully visible.
- The user can upload many photos at the same time.
- Each garment shows a status: pending, processing, ready or failed.
- A failed garment shows the reason. The user can retry or delete it.
- The user can edit any extracted attribute of a garment.
- The user can mark a garment as unavailable. An unavailable garment is not recommended.

### 4.4 The outfit request

- The user types a request in plain text. An example is "something for a warm day at the office".
- The user may attach a reference photo. The system reads the style from this photo. It does not add the photo to the wardrobe.
- The system needs at least one upper garment and one lower garment. It blocks the request if the wardrobe is too small.
- The system returns five outfits by default.
- Each outfit shows the garment thumbnails, a rendered image and a one line reason.
- Images appear one at a time as they finish. The user does not wait for all five.

### 4.5 Likes and the interest section

- The user can like or dislike each outfit.
- A liked outfit is saved with the garment IDs, the base image version and the render URL.
- The interest section lists all liked outfits. It is a plain database read. It never regenerates an image.
- A dislike is stored as a negative signal. It is not shown to the user again.

### 4.6 Limits

- Each user has a daily quota for image generation.
- The system rejects a request above the quota at the API layer.
- The system shows the remaining quota in the interface.

---

## 5. System architecture

### 5.1 The five layers

| Layer    | Component                  | Responsibility                                  |
| -------- | -------------------------- | ----------------------------------------------- |
| Client   | Web client                 | Upload, display, user input                     |
| Edge     | API service                | Authentication, validation, fast reads, enqueue |
| State    | Postgres, Redis            | Durable data, cache, locks, sessions            |
| Compute  | Celery workers             | All AI calls and all slow work                  |
| External | Gemini API, object storage | Model inference, file storage                   |

### 5.2 The core rule

**No AI call happens inside a web request.**

The API service must answer in under 300 milliseconds. A vision call needs three to eight seconds. An image render needs ten to thirty seconds. If the API waits for the model, one slow call holds one server worker. A few hundred users can then stop the service.

Every slow task goes to a queue. The API returns an ID at once. The client subscribes to updates.

---

## 6. The image ingestion pipeline

### 6.1 The steps

1. The client asks the API for a presigned upload URL.
2. The client sends the file directly to object storage. The file does not pass through the API.
3. The client tells the API that the upload finished. It sends the storage key.
4. The API writes one database row. The row holds the storage key, the owner ID, the kind and a `PENDING` status.
5. The API sends the row ID to the queue.
6. A worker takes the ID.
7. The worker takes a Redis lock on that ID.
8. The worker reads the row. It stops if the status is already `DONE`.
9. The worker sets the status to `PROCESSING`.
10. The worker reads the image and calls the vision model.
11. The worker writes the attributes and the embedding to the row.
12. The worker sets the status to `DONE` and releases the lock.

### 6.2 The recovery job

A scheduled job runs every two minutes. It finds two kinds of stuck rows:

- A row with a `PENDING` status older than five minutes.
- A row with a `PROCESSING` status older than ten minutes.

The job sends these IDs to the queue again. It increments an attempt counter. A row that passes the maximum attempt count moves to a `DEAD` status and raises an alert.

### 6.3 Failure classes

| Class     | Examples                                            | Action                                        |
| --------- | --------------------------------------------------- | --------------------------------------------- |
| Transient | Timeout, rate limit, 5xx response                   | Retry with an increasing delay                |
| Permanent | Corrupt file, no garment in photo, rejected content | Set `FAILED`. Store the reason. Do not retry. |

---

## 7. The recommendation pipeline

### 7.1 The three stages

**Stage 1 — hard filter.** Apply database rules. Remove garments that fail the season, the occasion or the availability flag. This stage is free and instant.

**Stage 2 — candidate selection.** If more than forty garments remain, reduce the set. Compare the request embedding against the garment embeddings with `pgvector`. Keep the closest items.

**Stage 3 — rerank.** Send the user profile, the request text and the surviving candidates to the language model as text. Ask for ranked outfits in strict JSON. Ask for a short reason for each outfit.

### 7.2 The exploration slot

Reserve one of the five results for a candidate that the filter would normally rank low. This keeps the results varied. It also creates feedback data on unexpected combinations.

### 7.3 The render stage

- Create one queue task per outfit. Do not create one task for all outfits.
- Each task sends the base image and the selected garment images to the image model.
- Each task writes the result to object storage. It then writes the URL to the outfit row.
- The client receives each result through Server-Sent Events.

---

## 8. Data model

### 8.1 Tables

| Table             | Key fields                                                                                                                             |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `users`           | `id`, `email`, `created_at`, `deleted_at`                                                                                              |
| `auth_identities` | `user_id`, `provider`, `provider_user_id`, `password_hash`                                                                             |
| `sessions`        | Held in Redis. Key is the session ID. Value is the user ID and the expiry.                                                             |
| `avatars`         | `user_id`, `base_image_key`, `profile_json`, `schema_version`, `status`                                                                |
| `garments`        | `id`, `user_id`, `image_key`, `content_hash`, `status`, `attributes_json`, `embedding`, `schema_version`, `attempts`, `failure_reason` |
| `requests`        | `id`, `user_id`, `prompt_text`, `reference_image_key`, `status`, `cache_key`, `created_at`                                             |
| `outfits`         | `id`, `request_id`, `garment_ids`, `rank`, `reason`, `render_status`, `render_key`                                                     |
| `feedback`        | `user_id`, `outfit_id`, `signal`, `created_at`                                                                                         |
| `quotas`          | Held in Redis. A token bucket per user per day.                                                                                        |

### 8.2 Notes on the schema

- `content_hash` allows deduplication. The same photo does not need a second AI call.
- `schema_version` marks which attribute format was used. It lets you find old rows when the schema changes.
- `garment_ids` is stored on the outfit. The outfit is therefore reproducible without the render.

---

## 9. Technology stack

| Concern          | Choice                        | Reason                                                                                              |
| ---------------- | ----------------------------- | --------------------------------------------------------------------------------------------------- |
| API framework    | FastAPI (Python)              | Async by default. Native Pydantic validation for strict model output. Same language as the workers. |
| Task queue       | Celery                        | Mature retry, scheduling and routing. Direct integration with FastAPI code.                         |
| Broker and cache | Redis                         | One system serves the queue, the cache, the locks, the sessions and the rate limits.                |
| Database         | PostgreSQL                    | Relational data with strong constraints. Transactions protect the status fields.                    |
| Vector search    | `pgvector` extension          | The data is small. A second database adds cost and a second failure point.                          |
| AI provider      | Gemini API                    | Strong vision understanding, structured JSON output and image generation in one provider.           |
| Object storage   | S3 compatible storage         | Presigned uploads. Private bucket. Signed read URLs.                                                |
| Client           | React with a modern framework | Component model suits the wardrobe grid and the progressive result panel.                           |
| Live updates     | Server-Sent Events            | Simple, one way, self recovering. No socket infrastructure needed.                                  |

---

## 10. Design decisions and the reasons

### 10.1 Text encoding instead of raw images at recommendation time

**The decision.** Extract the attributes of each garment one time. Store the text. Send only text to the recommendation model.

**The reason.** An image costs hundreds of tokens. Twenty images on every request is slow and expensive. A text profile of the same wardrobe is a few hundred tokens in total. The extraction cost is paid one time. Every later request is cheap.

**Second reason.** Text attributes are inspectable. You can see why two items were paired. You can add rules on top. You can test the logic. Raw image reasoning is a black box.

**The drawback.** Text loses visual nuance. Exact shade, pattern intensity and fabric drape are hard to describe.

**The mitigation.** Store an embedding of each garment image beside the text. The embedding carries the visual nuance. It is cheap and cacheable.

### 10.2 Write to the database before the queue

**The decision.** The API writes the row first. It sends the queue message second.

**The reason.** The database row is the only durable proof of the upload. If the process stops before the write, nothing is lost, because nothing was promised. If the process stops after the write, the recovery job finds the row.

**The rejected alternative.** Holding the pending URLs in process memory. Memory is lost on a restart. The image would then sit in storage with no record.

**The known gap.** The database commit can succeed and the queue publish can fail. This is the dual write problem. A transactional outbox solves it strictly. At this scale the recovery job is sufficient and much simpler.

### 10.3 Update the row, do not create a new object after the AI call

**The decision.** The row exists from the moment of upload. The worker updates it.

**The reason.** If the row is only created after a successful AI call, a crash produces an orphan image. The recovery job cannot find work that has no row.

### 10.4 One task per image and one task per outfit

**The decision.** Fan out. Never batch.

**The reason.** Tasks run at the same time. Total time equals the slowest task, not the sum. One failure does not destroy the other results. Retry granularity is correct: you retry one item, not twenty.

**The drawback.** More queue messages and more overhead per item. This cost is small compared to the AI call itself.

### 10.5 Server sessions in Redis instead of stateless JWT

**The decision.** Store the session server side.

**The reason.** The application holds body photos. If an account is compromised, the session must end immediately. A stateless JWT stays valid until it expires. You cannot cancel it.

**The drawback.** One Redis read per request. This costs under one millisecond. Redis becomes a dependency of every request.

### 10.6 A real photo as the base image

**The decision.** The primary path uses the user's own photo.

**The reason.** Virtual try-on works only if the user believes the result. A stylised avatar shows the outfit on a character, not on the user. Trust drops and the product loses its purpose.

**The drawback.** Body photos are sensitive personal data. Section 11 lists the required controls.

**The mitigation for privacy.** The selector based avatar is a full fallback. The rest of the pipeline only needs "a base image". It does not care about the source.

### 10.7 Filter before the model

**The decision.** Reduce the candidate set with rules and vectors before the language model sees it.

**The reason.** A long candidate list lowers accuracy. The model begins to confuse items. It also raises cost and latency.

**The drawback.** A rule can remove a bold combination that a human stylist would choose.

**The mitigation.** The exploration slot in section 7.2.

### 10.8 Store the render, not a provider URL

**The decision.** Copy every generated image into your own storage.

**The reason.** The interest section must never regenerate an image. A provider URL can expire. Your own object is permanent and cheap to serve.

### 10.9 Delete the cache key on write

**The decision.** When a like changes the interest list, delete the cached list. Do not update it in place.

**The reason.** Deletion cannot produce a wrong value. In place updates can. The next read rebuilds the cache correctly.

### 10.10 Redis serves five separate jobs

| Job          | Key shape            | Note                                                 |
| ------------ | -------------------- | ---------------------------------------------------- |
| Sessions     | `sess:{id}`          | Expiry equals the session lifetime                   |
| Result cache | `rec:{hash}`         | Hash of profile version, wardrobe version and prompt |
| Worker locks | `lock:{row_id}`      | Time limit longer than the task                      |
| Rate limits  | `quota:{user}:{day}` | Token bucket                                         |
| Queue broker | Celery internal      | Messages only                                        |

**The warning.** Redis holds data in memory. It can lose data on a restart. Postgres is the source of truth. Everything in Redis must be rebuildable.

---

## 11. Privacy and security requirements

1. The storage bucket is private. There is no public read access.
2. Every image is served through a signed URL with a short time limit.
3. Objects are encrypted at rest.
4. The user has a delete control. The delete removes the database rows and the storage objects.
5. Outfits are private by default. There is no public listing in the first release.
6. Uploads are validated for file type and size at the API layer.
7. The API never accepts an arbitrary image URL from the client. It issues presigned URLs instead.
8. Check the data retention terms of the AI provider tier before sending body photos.

---

## 12. Future scope (post-MVP)

The following features are out of scope for the first release. They are recorded here so the current schema does not block them.

### 12.1 Google login

Add "Login with Google" beside the email form. Use the OAuth 2.0 Authorization Code flow with PKCE. Verify the returned ID token signature on the server.

Link a Google identity to an existing account by the verified email address. The `auth_identities` table already supports this. The `users` table does not change.

The same table then supports Apple, Instagram or any later provider.

### 12.2 Weather based suggestions

Read the user's location. Call a weather API for the current and forecast conditions. Pass the temperature, the rain probability and the wind to the recommendation stage.

The weather becomes a hard filter input in stage 1. A heavy coat is removed on a warm day. A light shirt is removed on a cold day.

Cache the weather response per city for about thirty minutes. Many users share one city. One API call can serve all of them.

The garment schema must already carry a temperature range and a rain suitability flag. Add these fields to the extraction prompt now, even though nothing reads them yet.

### 12.3 Event and occasion based suggestions

Let the user select an occasion instead of typing it. Examples are office, casual, party, wedding and gym.

Each occasion maps to a formality range and to a set of allowed categories. The occasion then acts as a hard filter in stage 1 before the model runs.

The garment schema must already carry a formality level. Store it as a small ordered scale. This lets the filter compare items without a model call.

### 12.4 Social features

Add follow and following. Let a user share selected outfits.

Use fan out on read for the feed. Ask for the posts of the followed accounts and sort at read time. This needs one query and no extra storage.

Do not use fan out on write. It creates one write per follower for every post. This is unnecessary at the expected scale.

Sharing must be an explicit action for each individual outfit. A single control must never make the whole interest section public.

---

## 13. Build order

Build in this order. Each step produces something testable.

1. Login, sessions and the empty wardrobe screen.
2. Presigned uploads. Rows and statuses only, with no AI.
3. The worker and the attribute extraction. Watch the status change.
4. The recovery job and the retry logic. Break things on purpose here.
5. The recommendation stage with text output only. No images.
6. The render stage and progressive delivery.
7. Likes and the interest section.
8. Quotas and cost controls.

Do not build steps 5 and 6 together. Test the recommendation quality as text first. Text is cheap to test. Most of the product value sits there. The rendered image only displays a decision that the earlier stage already made.

---

## 14. Open questions

1. What is the minimum wardrobe size for a useful recommendation?
2. Should the system detect duplicate garments across uploads and merge them?
3. How long should a failed render stay visible before automatic removal?
4. Should the user be able to force a specific garment into an outfit request?
5. What is the acceptable cost per outfit request at the target user count?
