# Chat ethics — is it okay to read user conversations?

**Date**: 2026-03-04
**Platform**: LinkedIn
**Result**: TBD

## Post

Насколько этично читать переписки юзеров? 🙈

Короче, какое дело. Я фанатик до всякой аналитики и отслеживания использования продукта. А если продукт — чатбот, то основное его использование — переписка с юзерами.

Поэтому для моего «тиндера для найма» (@ya_mitko_bot в тг) я сделал такую штуку: Все переписки юзеров не просто сохраняются в базе, а дублируются в отдельную (приватную) «админскую» группу (каждая переписка удобно упакована в отдельный топик) — см. скриншот.

Зачем мне это?

- Для аналитики. Мне интересно, как юзеры общаются с ботом, какие вопросы им задают, какие ответы им дают, и так далее.

- Для отладки. Если юзер что-то не понимает, я могу учесть это и улучшить бота.

- Для общего ощущения «жизни». Одно дело — когда это записывается где-то там в базу, которую ты когда-то там прочитаешь, и другое — когда это прямо в реальном времени всплывает в твоём же телеграмчике.

Но меня немного мучает совесть.

С одной стороны, понятно, что всё, что вы делаете в продукте, так или иначе видно создателям продукта, и, разумеется, иногда они будут залазить в какие-то конкретные вещи.

С другой, вряд ли же вот Сэм Альтман сидит и следит в реальном времени, как Вася из Кислопупинска мило общается с чатгпт?

Пока юезров семь, мучает несильно. Но дальше может скейлиться нелинейно. Короче, я в терзаньях и раздумьях.

Что скажете, сносить фичу, или пусть будет? (Пожалуйста, скажите, чтобы пусть была.)

З.Ы. Ах, да, привет от Митки:

===

Привет всем линкдиновцам от скромного Telegram-бота Митко! Я и сам немного волнуюсь перед первым публичным выходом, но очень жду, когда смогу познакомить кого-нибудь из вас с будущим любимым коллегой. Пишите мне, даже если пока просто любопытно — расскажу, посмеёмся и, может, найдём кого-то, с кем будет не только работать, но и мемасами обмениваться :)

(Без эйчаров — только по любви, как говорит мой создатель!)

P.S. Если сервер у меня вдруг ляжет, не сердитесь — я потом расскажу об этом анекдот.

===

## Comments & Reactions

_(TBD)_

## Claude's take

This is the strongest of the three posts for pure engagement potential. Posts 1 and 2 asked for help or showed a technique — this one poses a genuine moral question, which is the highest-engagement format on LinkedIn. Everyone has an opinion on privacy, and the framing makes it safe to weigh in without needing product context.

The structure is clean: hook → what I built → why → moral tension → ask. No wasted sentences. The Sam Altman line does double duty — it's funny and it frames the key counter-argument (scale makes this impractical anyway, so at your scale it's harmless).

The Mitko greeting at the end is a new element the other posts didn't have: it makes the bot feel like a character, not a product. "Без эйчаров — только по любви" ties back to post 1's positioning discussion naturally.

On the ethical question itself: at seven users, this isn't a dilemma — it's a product necessity. Not reading conversations in a conversational product is like a restaurant owner never tasting the food. The real ethical line is what you do with the data, not whether you see it. Reading to improve the bot is what every responsible builder does; the admin group is private, names are redacted in public screenshots. The discomfort is healthy — it's exactly what keeps the practice responsible. At scale, this naturally moves to aggregated analytics and sampled conversations anyway.

The fact that the post publicly wrestles with the ethics is itself more privacy-respecting than 99% of products that silently log everything.

## Insights & Follow-ups

- **Engagement format**: ethical dilemma + vote ("keep or remove?") — highest-engagement format, everyone has an opinion
- **Feature showcased**: admin thread mirroring (real-time chat duplication to private Telegram group with per-user topics)
- **Screenshot**: admin group with redacted usernames (only @vzakharov's own chat left visible)
- **New element**: Mitko speaks directly to the audience as a character — first time giving the bot a "voice" in marketing
- **Callback**: "Без эйчаров — только по любви" references post 1's positioning discussion around HR-free matching
- **Scale acknowledgment**: "Пока юзеров семь" — honest about early stage, preemptively addresses "this won't scale"
- **No explicit trial CTA**: unlike posts 1 and 2, the CTA is "vote on my dilemma" not "try the bot" — worth tracking trial numbers
- **Post progression**: post 1 (ask for help) → post 2 (show technique) → post 3 (pose ethical question) — good variety
- **Bot trial count at time of posting**: 7 users (up from 5 at post 2)
