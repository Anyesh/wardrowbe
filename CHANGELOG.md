# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.11.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.10.3...wardrowbe-v1.11.0) (2026-10-06)


### ✨ Features

* **auth:** let a verified sign-in reclaim an email held by an unverified account ([42f59a6](https://github.com/Anyesh/wardrowbe/commit/42f59a6921aaddf329c316ba76caf47b1c426430))


### 🐛 Bug Fixes

* **analytics:** show a 0% acceptance rate and 0 rating instead of no data ([4d81f67](https://github.com/Anyesh/wardrowbe/commit/4d81f673bb5915aaa2a9c9ae405a49b2a7c9a081))
* **api:** treat a zero coordinate or rate as a value instead of missing ([c3dce51](https://github.com/Anyesh/wardrowbe/commit/c3dce5150d2db8d60d488077ceeae8ac70b6e8f4))
* **auth:** accept the string "true" for email_verified, as Apple sends it ([b6896e4](https://github.com/Anyesh/wardrowbe/commit/b6896e4937dd6880a5797cf0fc46a8bdffbd7dae))
* **auth:** fit IdP names and avatar URLs to their columns and fill a blank name from the token email ([6183d21](https://github.com/Anyesh/wardrowbe/commit/6183d214a9256901aa6687656ebcee944e006b6f))
* **auth:** flatten control characters in the IdP display name instead of refusing sign-in ([d431c96](https://github.com/Anyesh/wardrowbe/commit/d431c96b534d86aa3501c012c09a32f1b22ea9e9))
* **auth:** lock both rows in id order so two accounts swapping emails cannot deadlock ([656823f](https://github.com/Anyesh/wardrowbe/commit/656823f424edc4d9117046cccbca74771d0caa5c))
* **auth:** make a concurrent first sign-in idempotent ([700aa4c](https://github.com/Anyesh/wardrowbe/commit/700aa4c438794e140badc22d5372b9643d12d489))
* **auth:** make a concurrent first sign-in idempotent ([3eecd8b](https://github.com/Anyesh/wardrowbe/commit/3eecd8b4d91c041a60531b9de344244784015201))
* **auth:** never adopt an account whose email the identity source did not verify ([2cd630a](https://github.com/Anyesh/wardrowbe/commit/2cd630a9004cd372f0fd6efef952b93dda7ac550))
* **auth:** only trust email_verified when the id_token carries the same email ([f98226f](https://github.com/Anyesh/wardrowbe/commit/f98226f4e94d58d338753b5e7e8c0e0f41ab7099))
* **auth:** refuse email adoption for unverified sign-ins inside the user service ([2723716](https://github.com/Anyesh/wardrowbe/commit/2723716cbb9e96ba36ef9fd8f9197a4d21ebb10a))
* **auth:** retry lost sign-in races against committed rows instead of returning 500 ([cc8f966](https://github.com/Anyesh/wardrowbe/commit/cc8f966aa0f859a8ee50e2d48ab1e7ec52f7a6c8))
* **auth:** retry when a twin sync already moved this account to the new email ([7737075](https://github.com/Anyesh/wardrowbe/commit/7737075a0e913f99ce9acab9698d6248ab664569))
* **auth:** return 409 instead of 500 when a concurrent sync claims the same email ([e3f9276](https://github.com/Anyesh/wardrowbe/commit/e3f92767be8a96cd0cab18a0c7324fb63951441d))
* **auth:** treat a row with the caller's external_id as its own during a first sign-in race ([c36c14c](https://github.com/Anyesh/wardrowbe/commit/c36c14c406e1b04f09c3db1b40f23ee9e552be86))
* **auth:** validate the OIDC email claim with the shared email rule ([b8d9d38](https://github.com/Anyesh/wardrowbe/commit/b8d9d38bdcb818315827f2054bf31720e7d9230c))
* **colors:** collapse every Unicode whitespace run the same way in SQL, Python and the frontend ([2bf4822](https://github.com/Anyesh/wardrowbe/commit/2bf4822e00b24bc9f5e4c0aca3d6cab003e521a3))
* **colors:** derive every colour list and swatch from the vocabulary ([b831459](https://github.com/Anyesh/wardrowbe/commit/b83145900604dd0c18ea424ff868be5e61032f8c))
* **colors:** drop zero-width spaces, word joiners and BOMs so an invisible name reads as blank ([e2f6154](https://github.com/Anyesh/wardrowbe/commit/e2f615477f897b6a66d7a89c438c17afd67c4b68))
* **colors:** lowercase, trim and hyphenate colour names in the alias migrations ([21e2b76](https://github.com/Anyesh/wardrowbe/commit/21e2b76be7b0533ad9c392020c0c46a74c4e9e82))
* **colors:** normalise colour aliases in item filters and outfit palettes ([90c23fa](https://github.com/Anyesh/wardrowbe/commit/90c23fac99a4fb37113e8d78481d640a90e65de1))
* **colors:** normalise colour aliases on item and preference writes ([bf99cf0](https://github.com/Anyesh/wardrowbe/commit/bf99cf0fe23190b46091537c0ecdc45da0b330b5))
* **colors:** read spaced colour names as their hyphenated vocabulary colour ([d906d29](https://github.com/Anyesh/wardrowbe/commit/d906d290646162ce13e55dd55abfc05a8c35aa48))
* **colors:** remap colour names stored in learned profiles ([0972b76](https://github.com/Anyesh/wardrowbe/commit/0972b769d97bb5b726e29cb35411973523aee4bf))
* **colors:** remap stored frontend-only colour names ([252b3ee](https://github.com/Anyesh/wardrowbe/commit/252b3ee3470822317de932a1f0d89481b4627a7a))
* **compose:** pass the same backend env to every worker ([1d7f8fb](https://github.com/Anyesh/wardrowbe/commit/1d7f8fb6cf1917f39532b4d4dc1f1d547c3c76ef))
* **db:** commit the request session before the response is sent ([4be2264](https://github.com/Anyesh/wardrowbe/commit/4be2264b47ad113bb6b4e8346650b8f0fe41fad5))
* **email:** accept any RFC 5322 atext bare login as the sender ([f1d34f0](https://github.com/Anyesh/wardrowbe/commit/f1d34f08d956a99db195220865fa623093ab8329))
* **email:** collapse line breaks in the subject and sender name so legacy family names still send ([64bf966](https://github.com/Anyesh/wardrowbe/commit/64bf9660d3d461cb03e412c39affdb23fbbf92c4))
* **email:** encode a non-ASCII sender name apart from the address in From ([bb3c873](https://github.com/Anyesh/wardrowbe/commit/bb3c87310a7ebe9e6ea3dc3cb16e24176817959f))
* **email:** fail once on an unusable sender or a permanent SMTP refusal instead of retrying ([1823e9e](https://github.com/Anyesh/wardrowbe/commit/1823e9e306352d2f95e331dcc8448ccb31e5db1b))
* **email:** log an unvalidated sender once with the validator's reason ([9a432f0](https://github.com/Anyesh/wardrowbe/commit/9a432f09ce032830b77b330909ee856ecc89151a))
* **email:** send a quoted sender local part without quoting it twice ([ff9daef](https://github.com/Anyesh/wardrowbe/commit/ff9daef133391a3fd8c6d670c8d1e5300ba0260e))
* **email:** send from a sender the header parser cannot read instead of failing every retry ([b0a340b](https://github.com/Anyesh/wardrowbe/commit/b0a340ba5c624bd5b17c7a0f43dc374e23bcb6f3))
* **email:** send from the IDNA form of the sender and name the address that needs SMTPUTF8 ([54a6007](https://github.com/Anyesh/wardrowbe/commit/54a6007481d920841920f324f8d684193929fbba))
* **email:** send to the IDNA form of a domain and name the SMTPUTF8 gap for non-ASCII local parts ([15d5a39](https://github.com/Anyesh/wardrowbe/commit/15d5a3915d9d885007999f3d687c4918b1e6ab3f))
* **email:** stop retrying a send the mail server refuses for lack of SMTPUTF8 ([23da5f9](https://github.com/Anyesh/wardrowbe/commit/23da5f91272123fe6c6db6350641d69cbf9db21b))
* **email:** warn when SMTP_FROM_EMAIL looks like an address but is not one ([5d49927](https://github.com/Anyesh/wardrowbe/commit/5d4992779e1c02748530a25b0b9a1dc0c021dd6d))
* **families:** check invite addresses with the sign-in email rule before saving the invite ([03fd037](https://github.com/Anyesh/wardrowbe/commit/03fd0372124a3260e74646588ca5f9eb7a964089))
* **families:** escape the inviter and family names in the invite email ([5911dfb](https://github.com/Anyesh/wardrowbe/commit/5911dfbb8ba8709b23f01518fa1d85a4bdd9bb0e))
* **families:** require a verified email to accept an email-bound invite ([6e06243](https://github.com/Anyesh/wardrowbe/commit/6e06243541bd2a671f258f3bacb213cd8b3332bd))
* **families:** tell the inviter when the invite email did not go out ([dd18c38](https://github.com/Anyesh/wardrowbe/commit/dd18c3856a6c2b7b8dc3fbd0837587bef66b00ac))
* **family:** find the current member by user id so a detached admin keeps admin controls ([213e142](https://github.com/Anyesh/wardrowbe/commit/213e142c28c98d8bba1bd6d5548ab634e3e103c3))
* **family:** wait for the current member before listing others or deciding admin controls ([9971871](https://github.com/Anyesh/wardrowbe/commit/9971871e6b17cfd235cb04a4cd12291bc6a0de88))
* **frontend:** read today and weather shapes from one place ([f2edcad](https://github.com/Anyesh/wardrowbe/commit/f2edcad25799194cdf4eb024571031de8a4da123))
* **history:** show skipped outfits and filter every status ([e5eb35d](https://github.com/Anyesh/wardrowbe/commit/e5eb35dc96589ea9da5407191e3c5657d6229c98))
* **i18n:** capitalise the Italian accepted status label ([5855882](https://github.com/Anyesh/wardrowbe/commit/58558827121aa439dc7ec488f5093999d0c36d41))
* **items:** refresh outfit caches when an item's images change ([75f304e](https://github.com/Anyesh/wardrowbe/commit/75f304e1bf967ee29906bd0dc4e7d3a065812653))
* **learning:** drop non-numeric learned colour scores at runtime and in the remap migration ([603b026](https://github.com/Anyesh/wardrowbe/commit/603b02681946a796aa92b012c6318dfeca43bd9f))
* **learning:** keep the readable fields of a learned pattern instead of dropping the entry ([7944222](https://github.com/Anyesh/wardrowbe/commit/7944222437fce85d0607f1a4e265f6d1d705652f))
* **learning:** read learned scores and patterns through accessors that skip malformed entries ([cac6fda](https://github.com/Anyesh/wardrowbe/commit/cac6fda39e17863f948c914eb9af54aa896828ad))
* **learning:** report a 0% acceptance rate as the suggestion confidence instead of none ([d774df5](https://github.com/Anyesh/wardrowbe/commit/d774df5997fd771887911dda562dbb6b05b4abc9))
* **learning:** skip learned scores too large to read as a float ([b6f309a](https://github.com/Anyesh/wardrowbe/commit/b6f309a5dc5c96e51232c8381a75b49dec6243a4))
* **mattermost:** escape list markers after a bare carriage return ([63cd3dd](https://github.com/Anyesh/wardrowbe/commit/63cd3dd89242a1ccc49610b87e1f518b6be3ff37))
* **mattermost:** send a linked attachment title unescaped since Mattermost shows it as plain text ([1ffcb5b](https://github.com/Anyesh/wardrowbe/commit/1ffcb5b1e205999dbe720a4b225f85afc3bcf4c6))
* **migrations:** apply the colour rule in Python so unknown names lowercase as runtime writes do ([5b6cd7c](https://github.com/Anyesh/wardrowbe/commit/5b6cd7cab9d16f0eeeedaceafd24f0fc1c1ccb9f))
* **notifications:** bind the sent status through the outfit status enum type ([43ccd5e](https://github.com/Anyesh/wardrowbe/commit/43ccd5eb3bbb5fac486ace128ed985cf2c8f9cbb))
* **notifications:** build links and SMTP config from Settings ([970788e](https://github.com/Anyesh/wardrowbe/commit/970788e6f5b186118ce36ff7e23a915194ec2c44))
* **notifications:** check scheduled users for channels through the dispatcher ([1130f65](https://github.com/Anyesh/wardrowbe/commit/1130f659a4e385727e53621b87e07ac3690c9069))
* **notifications:** clear the earlier error when a retried notification is sent ([bd18027](https://github.com/Anyesh/wardrowbe/commit/bd18027f418064bee48ee4476d92a77e712a59ff))
* **notifications:** don't pre-fill an undeliverable .invalid address into an email channel ([c06cf1c](https://github.com/Anyesh/wardrowbe/commit/c06cf1cc796d49c432f2f317a35029e6463691ab))
* **notifications:** escape line-start markdown and the attachment title sent to Mattermost ([abfdedc](https://github.com/Anyesh/wardrowbe/commit/abfdedc691f682c4c97879a0cc4259c629b87c03))
* **notifications:** escape markdown and mentions in user text sent to Mattermost ([758e429](https://github.com/Anyesh/wardrowbe/commit/758e429e52b882f45dfd43b440beeb1fbc6a0f0e))
* **notifications:** flag a stored channel config that is not an object and keep it out of test errors ([6a5cba6](https://github.com/Anyesh/wardrowbe/commit/6a5cba670ceb61ec7ce749cba9a87fa960b9c5ed))
* **notifications:** flag stored channel settings this version rejects instead of failing silently ([87585fb](https://github.com/Anyesh/wardrowbe/commit/87585fbc969b022da79139ee5c2bd7fd4f7c99e4))
* **notifications:** keep a verdict the user gives while the outfit notification is sending ([88321d1](https://github.com/Anyesh/wardrowbe/commit/88321d19eaeb7f78d85ee046bb3b18e15561de96))
* **notifications:** keep the outfit greeting, weather line and short push body ([bbade4b](https://github.com/Anyesh/wardrowbe/commit/bbade4be3c34c5faa8f25d1a337d63a63cb3d0c0))
* **notifications:** keep the user's verdict when a retried outfit notification lands ([2ba0159](https://github.com/Anyesh/wardrowbe/commit/2ba01598987cdb792f321f6895b114fb0a5eb7c9))
* **notifications:** label retried outfits Today or Tomorrow from the outfit date ([1a15a11](https://github.com/Anyesh/wardrowbe/commit/1a15a112751d6b51d258862cdc527fb25bd2a312))
* **notifications:** mark the outfit sent when a retried notification goes out ([88c2c1e](https://github.com/Anyesh/wardrowbe/commit/88c2c1e3f44859021baaf3de41828946d3b15193))
* **notifications:** name a past outfit's weekday instead of calling it today ([387a486](https://github.com/Anyesh/wardrowbe/commit/387a486b2b4ca3eaba1d326aeb240a90f37f92e4))
* **notifications:** record each failed laundry channel with its own error and retry on the next run ([5ab5f80](https://github.com/Anyesh/wardrowbe/commit/5ab5f809db83c35b11c1d75f1519d1ef86460951))
* **notifications:** record every outfit channel attempt through the laundry recorder ([2612955](https://github.com/Anyesh/wardrowbe/commit/2612955426131593590f242d794197263995afdf))
* **notifications:** record the laundry channels that failed before a fallback succeeded ([44f9a00](https://github.com/Anyesh/wardrowbe/commit/44f9a00d6de87f264cea5ab1e00c105b9a2d32f6))
* **notifications:** restore the structured outfit email and Mattermost formatting ([0a78107](https://github.com/Anyesh/wardrowbe/commit/0a781073d72626468ba35b35d870354dbcad165d))
* **notifications:** retry the first channel that failed transiently, not a rejected config ([f9c4ec5](https://github.com/Anyesh/wardrowbe/commit/f9c4ec5843347e9601b2195dbc1fbd42002882e7))
* **notifications:** send laundry reminders through the same channel registry as the dispatcher ([0bf2b4b](https://github.com/Anyesh/wardrowbe/commit/0bf2b4b85a6cc20f27366e6ffa63d9c72b00817b))
* **notifications:** show channels registered by the mobile app ([1c0677d](https://github.com/Anyesh/wardrowbe/commit/1c0677d2c11faa4d6c5254c7eb2671643070da44))
* **notifications:** skip stored channels this version has no provider for ([1de3965](https://github.com/Anyesh/wardrowbe/commit/1de39650ac5c5895fe1a16041cb869b6561877e9))
* **notifications:** stop retrying a notification whose retry fails for good ([04ef598](https://github.com/Anyesh/wardrowbe/commit/04ef598d531dbe075be615f9d38cd05cb0fa8fb9))
* **notifications:** title outfits by occasion and show whole degrees with the degree sign on every channel ([0e23e90](https://github.com/Anyesh/wardrowbe/commit/0e23e905e4103b51e360ad7fcfe63419387fe530))
* **notifications:** treat a stored channel this version cannot send to as not found ([4b9b09e](https://github.com/Anyesh/wardrowbe/commit/4b9b09e74076d3f3554b8e97a11d3ed4b2d4e189))
* **notifications:** use the singular for a one-item laundry reminder ([f2cce86](https://github.com/Anyesh/wardrowbe/commit/f2cce863315960bf040f31d5fe8255c13f0a866a))
* **occasions:** give every occasion a formality range ([5d8f0d9](https://github.com/Anyesh/wardrowbe/commit/5d8f0d9d5c2b327b1d59f00445442acda18b2553))
* **occasions:** validate suggestions and schedules against one occasion list ([f4b3749](https://github.com/Anyesh/wardrowbe/commit/f4b374954f6cffe1a080da88d7b9d910a8c98a79))
* **occasions:** validate the default and wear-log occasions and read unlisted stored defaults as casual ([e5f581c](https://github.com/Anyesh/wardrowbe/commit/e5f581cfda7557e77ab901124d36da3a71569e78))
* **outfits:** default wear dates to the user's local day ([41ac74f](https://github.com/Anyesh/wardrowbe/commit/41ac74fc12a8c4a9cd4042640c056df6f4d78d50))
* **outfits:** one Outfit type shaped like the API response ([b8f7d4a](https://github.com/Anyesh/wardrowbe/commit/b8f7d4a47e770822d891af0dbee190e5ed2c496e))
* **outfits:** record mark-worn on the user's local day ([cf9c2ab](https://github.com/Anyesh/wardrowbe/commit/cf9c2ab6842a11daed7bc498dba3d63c031c56ee))
* **services:** rule drifts and bug fixes ([1f6f6f4](https://github.com/Anyesh/wardrowbe/commit/1f6f6f49150dc2cc4fe6d0b28460213e9d461e52))
* **settings:** cap the location name at its column width and show one translated save error ([55ed807](https://github.com/Anyesh/wardrowbe/commit/55ed80796473f1d5b26c3957d3c89d07fa6260e7))
* **studio:** record an undated mark-worn outfit on the user's today ([dede24e](https://github.com/Anyesh/wardrowbe/commit/dede24e52b12684e0ca7c2a334f000267adeedc5))
* **timezone:** fall back to UTC in the browser as the backend does ([e84bb99](https://github.com/Anyesh/wardrowbe/commit/e84bb99b7468e422915f758bb3be38752e2a24c0))
* **timezone:** resolve every user timezone through one helper and validate new ones ([fab5c59](https://github.com/Anyesh/wardrowbe/commit/fab5c59247631527a0b6032c25fb8205ddf244ae))
* **uploads:** enforce MAX_UPLOAD_SIZE_MB per file ([14f8aaf](https://github.com/Anyesh/wardrowbe/commit/14f8aafa2cad1e8d6154030a230ce3f3e1168258))
* **uploads:** name failed files and only offer retry for retryable ones ([f093659](https://github.com/Anyesh/wardrowbe/commit/f0936596b8280d16754acee66c83a6e97c13cc3e))
* **users:** accept the same email addresses everywhere sign-in does ([19dd7c3](https://github.com/Anyesh/wardrowbe/commit/19dd7c3e811cf9ed70fa8d31c46763342b0f1dd3))
* **users:** bound profile updates to the column limits instead of failing the flush ([3321158](https://github.com/Anyesh/wardrowbe/commit/3321158dedf1af2af3b2bdef67f01963c1006604))
* **users:** count a name of combining marks alone as blank ([66ce72c](https://github.com/Anyesh/wardrowbe/commit/66ce72c7145b5aaf9bbea353957bb487d071d45e))
* **users:** count interlinear annotation and Egyptian format controls as blank ([d338d23](https://github.com/Anyesh/wardrowbe/commit/d338d23eff712ed614fc94c25c0fdb8fb940cf2b))
* **users:** keep rejecting .invalid and .onion email domains ([1b0e469](https://github.com/Anyesh/wardrowbe/commit/1b0e4695524b9964078324791846e78d50e5adf3))
* **users:** match blank names on Unicode's default ignorable ranges instead of every format character ([0f5bcd7](https://github.com/Anyesh/wardrowbe/commit/0f5bcd78821db0e1a97506701ae1be3de1387f5c))
* **users:** refuse a body measurement too large to read as a float ([4e79c23](https://github.com/Anyesh/wardrowbe/commit/4e79c2341e927f36ea9333adbebbbf516bbffbaa))
* **users:** refuse line breaks in the location name ([1882226](https://github.com/Anyesh/wardrowbe/commit/18822266e266f4fdc95a20827b6b69b41a58d7a8))
* **users:** refuse names that are only whitespace or zero-width characters ([62f1c01](https://github.com/Anyesh/wardrowbe/commit/62f1c013653136b181e71b02da9cff9225e388f6))
* **users:** treat names made only of invisible characters as blank, also after the IdP cut ([b18bed8](https://github.com/Anyesh/wardrowbe/commit/b18bed8799a9beb1b672e93146b6107e07df87a1))
* **validation:** refuse line breaks and control characters in family and display names ([7ab28e3](https://github.com/Anyesh/wardrowbe/commit/7ab28e359e134010eeffeea3a4c0239446d44344))
* **wardrobe:** count worn-ago days across daylight-saving changes ([374c4cb](https://github.com/Anyesh/wardrowbe/commit/374c4cb3bbdf6c8571041b845cb137a249d94966))
* **wardrobe:** paint item colour dots through the shared colour lookup ([7763da4](https://github.com/Anyesh/wardrowbe/commit/7763da46ffaa49b222cc01324995ee9f75904495))
* **workers:** charge a retry attempt only for a failed send, not for a lock error ([f99c8c0](https://github.com/Anyesh/wardrowbe/commit/f99c8c01cfaf80c6dc67ac8a6414796ddeecc830))
* **workers:** keep a failed rollback and a lock release error out of the wrong log line ([49aa50d](https://github.com/Anyesh/wardrowbe/commit/49aa50def933392cba4688281b4d2183eb54c257))
* **workers:** roll back a failed notification retry so the rest of the batch still runs ([8fad78a](https://github.com/Anyesh/wardrowbe/commit/8fad78af09d732a71736f389800da54aff108de2))


### ♻️ Refactoring

* **email:** flatten header values with the shared control-character rule ([84fb5e0](https://github.com/Anyesh/wardrowbe/commit/84fb5e0fcaf85b15b62f453eec64c2d65c8c536a))
* **notifications:** build the laundry reminder message in one function ([3ec0c4e](https://github.com/Anyesh/wardrowbe/commit/3ec0c4e04c3cb693d7145d75ec325f3c36e1168a))
* **users:** drop the unused UserService.create/update and their schemas ([3f5ad4b](https://github.com/Anyesh/wardrowbe/commit/3f5ad4b2c4f003b3384a6c51fe0248cc7d287a6a))


### 📝 Documentation

* **auth:** note how commit order settles a reclaim racing the holder and when retries run out ([a76b83e](https://github.com/Anyesh/wardrowbe/commit/a76b83e6bdaeaeeabca2b3852003dfa5dd2cbb76))
* **notifications:** state the retryable rule instead of listing its current cases ([3287868](https://github.com/Anyesh/wardrowbe/commit/3287868de6cb67c227a9417fcc097a5599cbb8b5))
* **oidc:** replace the dead OIDC_SKIP_SSL_VERIFY with OIDC_CA_BUNDLE ([51f0f59](https://github.com/Anyesh/wardrowbe/commit/51f0f596e560b2127348b64b059a20f38f06e9a9))


### 🧪 Tests

* **auth:** cover case and padding variants of a detached address at /auth/sync ([4ac6026](https://github.com/Anyesh/wardrowbe/commit/4ac6026d6362bae4066b0f0ef870c46d8fcbd73f))
* **auth:** merge the two-session race helpers into one ([24a7126](https://github.com/Anyesh/wardrowbe/commit/24a71268771d37751c977ba4e82bdd60b8d3e1d7))
* **auth:** parametrize the adopt/refuse race and read the race outcome after every commit ([a7a67b3](https://github.com/Anyesh/wardrowbe/commit/a7a67b324c53d3486b084e2a618be7a90fccb937))
* **auth:** parametrize the OIDC sync tests behind one fixture and cover persisted email_verified ([2d8671d](https://github.com/Anyesh/wardrowbe/commit/2d8671d9c2c8a31ff55ce5bbb2b1ec774cb8e253))
* **auth:** read the session and family of a detached account ([2bd803b](https://github.com/Anyesh/wardrowbe/commit/2bd803bdfb63167af6ecc9132273a8d3177ee731))
* **auth:** split the adoption and changed-email tests into adopt, reclaim and refuse cases ([66d85b2](https://github.com/Anyesh/wardrowbe/commit/66d85b2e39ae2440aa49c8cd8d6c3d8dc3ab736e))
* **auth:** table the OIDC email claim cases and cover a punycode claim against a unicode body ([b85df9f](https://github.com/Anyesh/wardrowbe/commit/b85df9fe06d42a7616b335774dea4f148d44e3cc))
* **auth:** wait for the second sync to block on the first before committing ([b32e458](https://github.com/Anyesh/wardrowbe/commit/b32e4582a18032de7b72d3547b6db40d5e29f70c))
* **calendar:** seed the profile so the today test cannot race a timeout ([7b3dce3](https://github.com/Anyesh/wardrowbe/commit/7b3dce3bdde21a19b8c4e7aa21004154ccd0215f))
* **colors:** check each colour alias against the stored colours instead of a tautology ([5a3fc03](https://github.com/Anyesh/wardrowbe/commit/5a3fc035d19adca3321f6dbfa9e2f784fd6ae215))
* **db:** assert auth and endpoint share the request session on a route that uses both ([9b5151f](https://github.com/Anyesh/wardrowbe/commit/9b5151fba07785ac7829e1271f1333c1aeef8775))
* **families:** assert the invite 403 details and that the email match is checked first ([3230c83](https://github.com/Anyesh/wardrowbe/commit/3230c83eb7d1697d1e8e1f4d83d39b5074cbeef7))
* **history:** assert literal status labels instead of reading the catalog ([d45e4cd](https://github.com/Anyesh/wardrowbe/commit/d45e4cdbbfac2cf5204f715598bc1b4708b26983))
* **invite:** cover the unverified-email and wrong-email join errors ([8bc1874](https://github.com/Anyesh/wardrowbe/commit/8bc187426631450036d7a2fe3855d2f014db270b))
* **logging:** check each entrypoint's real app logger instead of a recorded call ([444cd1c](https://github.com/Anyesh/wardrowbe/commit/444cd1c5f0c7ec42e47ea02f954655b3be4533e7))
* make the observer stubs constructible under vitest 4 ([a217e0d](https://github.com/Anyesh/wardrowbe/commit/a217e0da97cfec3834c856e37fafa4108efdbc6d))
* **notifications:** check invite and notification email escaping in one table ([16072a1](https://github.com/Anyesh/wardrowbe/commit/16072a179038e3db7b9f5d62715f7d29f39f1877))
* **notifications:** check trailing-slash links once across outfit, laundry and invite emails ([be4e0bd](https://github.com/Anyesh/wardrowbe/commit/be4e0bd801f09f69d606d3b27ee4ea0afd427f1f))
* **notifications:** compare outfit renders with literal expected output ([7d1bd67](https://github.com/Anyesh/wardrowbe/commit/7d1bd67c6f0817974004ee55d4960568b61b218d))
* **notifications:** cover the first send in the verdict race test ([bf8777d](https://github.com/Anyesh/wardrowbe/commit/bf8777d4d76e012b5c6b59fda602b0993e9102ac))
* **notifications:** parametrize the single-channel laundry reminder tests ([d05962b](https://github.com/Anyesh/wardrowbe/commit/d05962b0bda4e4692244bc6090c521a4121cf6f3))
* **notifications:** split the retry status cases out of the day label test ([f8bed8a](https://github.com/Anyesh/wardrowbe/commit/f8bed8ab745f9abc66b01323bb0b264f6e46014b))
* **occasions:** drop the schedule occasion tests the shared vocabulary tests already cover ([6ad004f](https://github.com/Anyesh/wardrowbe/commit/6ad004f8cad72db0ea189dd9932f297f5be3e4b1))
* **preferences:** drop the unlisted default occasion test the shared occasion table covers ([8b721f5](https://github.com/Anyesh/wardrowbe/commit/8b721f598ebb169b9bd2255a624fb4251a1cb4ba))
* share one session_maker fixture and restore dependency overrides after real_get_db ([092a7d4](https://github.com/Anyesh/wardrowbe/commit/092a7d4079d836d1aba0ae974d2cd5232eb0af4e))
* **timezone:** cover UTC+13, Kathmandu and daylight-saving days in the user clock ([3a33ceb](https://github.com/Anyesh/wardrowbe/commit/3a33ceb736c1c8609cf7d91737d8136dbeb46003))
* **timezone:** parametrize the bad stored timezone reads and saves ([c5e455e](https://github.com/Anyesh/wardrowbe/commit/c5e455e9f2c8fc02885857f2850591a39ea126a5))
* **uploads:** table the failure codes with their retryable flag ([12ce25d](https://github.com/Anyesh/wardrowbe/commit/12ce25dee2b0df2acab685874a4511c82cd22091))
* **workers:** run the retry test through the real Redis lock and cover a missing user ([cac432c](https://github.com/Anyesh/wardrowbe/commit/cac432c6d73c2ec0167264cea13775813bf7acce))

## [1.10.3](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.10.2...wardrowbe-v1.10.3) (2026-10-01)


### 🐛 Bug Fixes

* give suit its own outfit slot and align the tagging vocabulary with the scorer ([68f66d4](https://github.com/Anyesh/wardrowbe/commit/68f66d47053634ebf391cc12ffeaa1a2b1ccd30f))
* **i18n:** make i18n:scan catch copy in option-list label properties ([4e702e3](https://github.com/Anyesh/wardrowbe/commit/4e702e3ebee613b620eb11d5d5674260125e4fc0))
* **learning:** record dresses, suits and mid layers in the outfit composition ([aa7480b](https://github.com/Anyesh/wardrowbe/commit/aa7480b430cc0bbc3586add6c4e513c4cb6ba94c))
* **studio:** make outfit warnings slot-aware and translate role, material and formality labels ([587363d](https://github.com/Anyesh/wardrowbe/commit/587363d19bdecf6024ec086e2db94aa4a6034337))
* **suggest:** translate the base-item type chips and type them against the vocabulary ([8c9e1c9](https://github.com/Anyesh/wardrowbe/commit/8c9e1c96c57f1842ba7cb3c14f190cfdc3c0ce2a))


### ♻️ Refactoring

* derive the tagging prompt and type lists from one vocabulary file ([abe2ada](https://github.com/Anyesh/wardrowbe/commit/abe2adadee4b3b523a0e88d2b1bca13ee0122a1c))
* **frontend:** generate the garment lists from the vocabulary file and check them in CI ([7a8faac](https://github.com/Anyesh/wardrowbe/commit/7a8faac3761a4e22563be47ab41f24b5b62aa73d))
* **frontend:** generate the garment lists from the vocabulary file and check them in CI ([986fd33](https://github.com/Anyesh/wardrowbe/commit/986fd33e4411e62429a82bd705ba180e66924635))


### 📝 Documentation

* list the vocabulary, prompt and generated dirs and the wider i18n scan in CONTRIBUTING ([7c45546](https://github.com/Anyesh/wardrowbe/commit/7c4554688289059596e224e7c757eb62e3a0d190))

## [1.10.2](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.10.1...wardrowbe-v1.10.2) (2026-09-30)


### 🐛 Bug Fixes

* **analytics:** count dresses as bases when judging layers ([f0616b5](https://github.com/Anyesh/wardrowbe/commit/f0616b54d894a9facd0875890eebbd06d2a1655c))
* **analytics:** derive tops/bottoms ratio from ITEM_ROLE ([754002f](https://github.com/Anyesh/wardrowbe/commit/754002f8384ee91365d27f283f3cef87e3340548)), closes [#209](https://github.com/Anyesh/wardrowbe/issues/209)
* **analytics:** judge layers against base tops in composition insight ([9c85d6d](https://github.com/Anyesh/wardrowbe/commit/9c85d6d6602eed67403139379c1f3576800fcab6)), closes [#209](https://github.com/Anyesh/wardrowbe/issues/209)
* **frontend:** refresh item edit form from latest item when entering edit mode ([9e53998](https://github.com/Anyesh/wardrowbe/commit/9e53998978c7a031e2164127fc92a3b7c51e4284))
* **i18n:** correct trucker, combat and camp-collar subtype translations ([418db8d](https://github.com/Anyesh/wardrowbe/commit/418db8d05aba21979b23c47e49aa0c7c6c9a45e1))
* surface rejected AI item types and make subtype editable ([#210](https://github.com/Anyesh/wardrowbe/issues/210)) ([27c4482](https://github.com/Anyesh/wardrowbe/commit/27c4482d052ce006afc0ad7accd460cbc9008cf8))


### 🧪 Tests

* keep CLOTHING_SUBTYPES in sync with the vision prompt ([e4dc1b3](https://github.com/Anyesh/wardrowbe/commit/e4dc1b3da4aad119413f329b2d32f3522e8bd89a))

## [1.10.1](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.10.0...wardrowbe-v1.10.1) (2026-09-18)


### 🐛 Bug Fixes

* **ai:** classify 200 error envelopes by message before stripping params ([752dcdf](https://github.com/Anyesh/wardrowbe/commit/752dcdf159c4680df444f9cde51b840a69bd19e1))
* **ai:** handle AI error envelopes returned with HTTP 200 ([e3e5a95](https://github.com/Anyesh/wardrowbe/commit/e3e5a950541aa31b4885c51bdb8f22565a69a808))
* **ai:** handle error envelopes in text generation ([9da5d95](https://github.com/Anyesh/wardrowbe/commit/9da5d95a0eae27baf080c05ce2117288dcd30b5e))
* handle AI error envelopes returned with HTTP 200 ([#201](https://github.com/Anyesh/wardrowbe/issues/201)) ([2804524](https://github.com/Anyesh/wardrowbe/commit/28045246da067fe185d728045adc46c74fd43e15))

## [1.10.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.9.0...wardrowbe-v1.10.0) (2026-09-11)


### ✨ Features

* **suggest:** add base item selection and 3-look comparison view ([#194](https://github.com/Anyesh/wardrowbe/issues/194)) ([6062793](https://github.com/Anyesh/wardrowbe/commit/6062793f9f862432f125548a9aa6d04f29f89f58))


### 🐛 Bug Fixes

* **ai:** bypass reasoning mode by default to prevent timeouts on thinking models ([129ef25](https://github.com/Anyesh/wardrowbe/commit/129ef256c9715efcfa4e56c3770b4f2bbb82f047))
* **ai:** bypass reasoning mode by default to prevent timeouts on thinking models ([ea8966e](https://github.com/Anyesh/wardrowbe/commit/ea8966e0caa86c2189e0667a0ede6355918cec5b))
* **recommendation:** support all-season items and weather-aware season scoring ([fd56d47](https://github.com/Anyesh/wardrowbe/commit/fd56d4798686d8d09d5ead1191cc14aea5ffb87e))
* **recommendation:** support all-season items and weather-aware season scoring ([bd08b13](https://github.com/Anyesh/wardrowbe/commit/bd08b13a657012af4d4ebdd5c1e98c4c58fab122))

## [1.9.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.8.2...wardrowbe-v1.9.0) (2026-09-03)


### ✨ Features

* blend outfit scoring across the day's temperature range ([dd1b8f8](https://github.com/Anyesh/wardrowbe/commit/dd1b8f8e5ad4ead2472e114cc4fdb303ec31b426))
* bulk-cancel in-progress AI analysis ([#152](https://github.com/Anyesh/wardrowbe/issues/152)) ([26f2cad](https://github.com/Anyesh/wardrowbe/commit/26f2cadaf861092e750c850df0b6d529eda3eb96))
* **ci:** add /reopen command for closed issues ([0f7046b](https://github.com/Anyesh/wardrowbe/commit/0f7046b01aae0bf0e0fffeb96cb4b3ad492907a6))
* **release:** notify reporters when a fix ships ([c4aeacf](https://github.com/Anyesh/wardrowbe/commit/c4aeacf6c9afeac88baad2036ceb62648fa68a8f))


### 🐛 Bug Fixes

* bound AI request concurrency and fix upload queue stall ([#152](https://github.com/Anyesh/wardrowbe/issues/152), [#154](https://github.com/Anyesh/wardrowbe/issues/154) reopened) ([bb441b6](https://github.com/Anyesh/wardrowbe/commit/bb441b63eedb61fea2a46601eefc8a6092ed8a55))
* bound AI request concurrency and fix upload queue stall ([#152](https://github.com/Anyesh/wardrowbe/issues/152), [#154](https://github.com/Anyesh/wardrowbe/issues/154) reopened) ([7a7e0c6](https://github.com/Anyesh/wardrowbe/commit/7a7e0c6ae46ae3f4f953cb107844427c00685d95))
* **ci:** Fix first time pr ([70ce6f9](https://github.com/Anyesh/wardrowbe/commit/70ce6f9d49b36fe1d9b7b91a8b86cb3513483968))
* **templates:** point issue template links at the real repo ([1b863bf](https://github.com/Anyesh/wardrowbe/commit/1b863bfb03ef9f5cd66219f35646055a57faf538))
* **worker:** make the arq pool the only AI concurrency bound ([d0170b8](https://github.com/Anyesh/wardrowbe/commit/d0170b83f42c6740ef2c5bde407da556ac1a0482))


### 👷 CI/CD

* add actionlint gate for workflow files ([3d163a1](https://github.com/Anyesh/wardrowbe/commit/3d163a1672bd76a58d1f31f4fde11d6db5d13173))
* assign PRs to the repository owner instead of a hardcoded login ([abb2d4d](https://github.com/Anyesh/wardrowbe/commit/abb2d4dddecd76f6444089c99efafd332ff7fe22))
* auto-assign PRs to maintainer ([0cf4b69](https://github.com/Anyesh/wardrowbe/commit/0cf4b69405d18d2172edc448ecdcf7bba8c19dbd))
* auto-label PRs by changed path ([129ccc6](https://github.com/Anyesh/wardrowbe/commit/129ccc603451b9c63145e050d8f967d1a7e2e4c6))
* document intentional word-splitting in docker-publish ([a7a1ea3](https://github.com/Anyesh/wardrowbe/commit/a7a1ea38811d3a953e8981cdbf59819b7bb6a0e3))
* enforce conventional-commit PR titles ([66808c9](https://github.com/Anyesh/wardrowbe/commit/66808c99b1965de92090c7f2244b81adb0786ac0))
* re-check PR title on synchronize ([9793a01](https://github.com/Anyesh/wardrowbe/commit/9793a01e05ec29bfb2b80a84800f8e680a470e36))
* run each test suite once and drop the missing frontend coverage script ([ae9c2c9](https://github.com/Anyesh/wardrowbe/commit/ae9c2c949e0faf1256fae59af509ceba1c5ea16b))
* welcome first-time issue and PR authors ([49be742](https://github.com/Anyesh/wardrowbe/commit/49be74277a03191d6c2e70f88aaab6b86b138fc2))
* welcome only true first-time authors ([89c1023](https://github.com/Anyesh/wardrowbe/commit/89c1023feb0a19b5ed707ad54d993afb63ee9377))

## [1.8.2](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.8.1...wardrowbe-v1.8.2) (2026-08-22)


### 👷 CI/CD

* build arm64 images natively instead of under QEMU ([4aae3a0](https://github.com/Anyesh/wardrowbe/commit/4aae3a0ff95b50797ce270b2e1af0f66fb4b118a))

## [1.8.1](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.8.0...wardrowbe-v1.8.1) (2026-08-22)


### 🐛 Bug Fixes

* **images:** honor EXIF orientation on upload ([#172](https://github.com/Anyesh/wardrowbe/issues/172)) ([68d730a](https://github.com/Anyesh/wardrowbe/commit/68d730a8d2ee846b65190a1898bb7927ec6b2c56))
* **users:** reject unknown fields on PATCH /users/me ([#168](https://github.com/Anyesh/wardrowbe/issues/168)) ([69bb1f6](https://github.com/Anyesh/wardrowbe/commit/69bb1f663415f126ab470bcffce7be54935d94d7))
* **wardrobe:** split bulk upload chunks that exceed the server's configured limit ([#175](https://github.com/Anyesh/wardrowbe/issues/175)) ([ec0fb17](https://github.com/Anyesh/wardrowbe/commit/ec0fb17f9cd13a7317d5ed52f4a7a24325e7684c))
* **wardrobe:** stuck upload queue records now durable and cancellable ([#163](https://github.com/Anyesh/wardrowbe/issues/163)) ([b89bc4f](https://github.com/Anyesh/wardrowbe/commit/b89bc4f35c19fa20731b274ba41a32784bd447f6))


### 🔧 Maintenance

* pin rembg to 2.0.81 ([d9ca598](https://github.com/Anyesh/wardrowbe/commit/d9ca5982183a446e33dd41c10be356567fbc2fc3))

## [1.8.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.7.0...wardrowbe-v1.8.0) (2026-08-15)


### ✨ Features

* external outfit authoring for suggestions and pairings ([#156](https://github.com/Anyesh/wardrowbe/issues/156)) ([1d3506a](https://github.com/Anyesh/wardrowbe/commit/1d3506a7bbab293e87043b6bfd9f996d7d1dffd6))
* **items:** add ai_failed_at column and retry cooldown config ([ebe8409](https://github.com/Anyesh/wardrowbe/commit/ebe8409a31ecdd5249c2e6b3461c2fdb23e0409b))
* **items:** add upload_key idempotency for bulk upload retries ([1d9d832](https://github.com/Anyesh/wardrowbe/commit/1d9d832dd41f7af1c34acf34957e2680fb83c4f7))
* **wardrobe:** add durable upload queue and drain manager ([0d0ba29](https://github.com/Anyesh/wardrowbe/commit/0d0ba293f4fd6187bd0973e541262eb1b8ac3cc4))
* **wardrobe:** show queued vs analyzing status with elapsed time ([9da07d0](https://github.com/Anyesh/wardrowbe/commit/9da07d06bea8c3caae2689692feb1cee04dc35c4))
* **wardrobe:** surface retry-cooldown status to the user ([a2848f4](https://github.com/Anyesh/wardrowbe/commit/a2848f46fbc305bd26d6956dadfb7ab1eed7fff2))
* **wardrobe:** wire durable upload queue into bulk-upload UI ([64ca39e](https://github.com/Anyesh/wardrowbe/commit/64ca39eae10db9dc452bfc72f23cc7fe2f6816b3))
* **worker:** make AI tagging concurrency configurable ([adafab9](https://github.com/Anyesh/wardrowbe/commit/adafab9f37caa12092e786dae36d43d2fcd5018b))


### 🐛 Bug Fixes

* **ai:** stop image preprocessing from blocking the event loop ([b6ad642](https://github.com/Anyesh/wardrowbe/commit/b6ad6420110962651653a3fe75d3d64d27047313))
* **items:** gate manual and bulk retry behind a cooldown after failure ([9338289](https://github.com/Anyesh/wardrowbe/commit/9338289a0a769ea2374d7127239700528c2e6d15))
* **items:** idempotent re-analysis and real queue visibility ([9c8cbfd](https://github.com/Anyesh/wardrowbe/commit/9c8cbfdd657479f1ad7dff3a035b8a77153e0ac6))
* regenerate frontend lockfile for musl/alpine platform ([961b09f](https://github.com/Anyesh/wardrowbe/commit/961b09ff59d819d859d9068b9b72e43144b6d711))
* **worker:** stop the stale-item sweep from condemning queued items ([cc52597](https://github.com/Anyesh/wardrowbe/commit/cc52597e8431f661789477a9d480964574c52cb6))


### 🧪 Tests

* **backend:** cover retry-cooldown claim, gating, and concurrency ([ec8778f](https://github.com/Anyesh/wardrowbe/commit/ec8778f65cdb58a482be809e8e08e03a441ed991))
* **backend:** cover stale-sweep, concurrency, and idempotency changes ([45ea759](https://github.com/Anyesh/wardrowbe/commit/45ea759735a6021d7813785ec3370609e08c878f))


### 👷 CI/CD

* remove unused cognitive-cache context workflows ([1604071](https://github.com/Anyesh/wardrowbe/commit/1604071981d779d62bce4b8423b2726ea8add56f))


### 💄 Styling

* ruff-format upload_key migration ([ced1ed8](https://github.com/Anyesh/wardrowbe/commit/ced1ed8eb0708c45293be97e10e4cd4bc4130d21))

## [1.7.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.6.0...wardrowbe-v1.7.0) (2026-07-30)


### ✨ Features

* add next-intl internationalization with 4 locales ([be2668f](https://github.com/Anyesh/wardrowbe/commit/be2668f9b326ddfaaa45ecb2aad9195fd74b4bc5))
* **backend:** persist user locale ([a1878d3](https://github.com/Anyesh/wardrowbe/commit/a1878d3bb07258ca1285dc1334d5c082d49e120b))
* **i18n:** restructure keys onto feature namespaces and ship 8 locales ([eaf47b3](https://github.com/Anyesh/wardrowbe/commit/eaf47b3dffb64fa430f2ead21ed1d2f7f7c3850e))
* **outfits:** add bulk-delete endpoint ([0db1be2](https://github.com/Anyesh/wardrowbe/commit/0db1be23417cad87d28fa498bac9d5bf409c41ff))
* **outfits:** add bulk-select/delete to outfits page, rename lookbook filter chip ([ea9f2c6](https://github.com/Anyesh/wardrowbe/commit/ea9f2c69decadb5f6e16f7e27ac1989bfbfe21e8))


### 🐛 Bug Fixes

* **frontend:** restore missing [@emnapi](https://github.com/emnapi) entries in package-lock.json ([58740db](https://github.com/Anyesh/wardrowbe/commit/58740db6f33b4ecbdd074a552205d3110625454b))
* **frontend:** sync package-lock.json with package.json ([8ce97d0](https://github.com/Anyesh/wardrowbe/commit/8ce97d0d47e6f9803fbe3b83c75b7700899ecd6f))
* **i18n:** translate defaultOccasion label in 6 locales ([6c92599](https://github.com/Anyesh/wardrowbe/commit/6c9259975146e9ec6be616b36583995d9f35c1cf))
* **outfits:** relabel Reject to Dismiss ([c54fd57](https://github.com/Anyesh/wardrowbe/commit/c54fd57e6713a48cf5a6d944c61a96fafdd9bf25))


### 📝 Documentation

* replace star history with supporters list ([0ba2f77](https://github.com/Anyesh/wardrowbe/commit/0ba2f77bb1dc72ac1ee04bc55354994cdd50a2ec))


### 👷 CI/CD

* gate translation coverage ([6a87d29](https://github.com/Anyesh/wardrowbe/commit/6a87d298b9b489f62eb0373cfc939f99362615e2))

## [1.6.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.5.1...wardrowbe-v1.6.0) (2026-07-25)


### ✨ Features

* add custom User-Agent header to JWKS client ([#134](https://github.com/Anyesh/wardrowbe/issues/134)) ([c18fa75](https://github.com/Anyesh/wardrowbe/commit/c18fa75a8fa70342466b7c84bf8cefbd0e4a51a7))
* defer item tagging to an external agent (phase 2) ([c63ced9](https://github.com/Anyesh/wardrowbe/commit/c63ced9caf4d4241fe53f7b164a886e45979547c))


### 🐛 Bug Fixes

* retry AI tagging without logprobs when the provider rejects it ([2fbf38f](https://github.com/Anyesh/wardrowbe/commit/2fbf38fe2d0f3811edef385fabe4b168ee12e84e))
* retry AI tagging without logprobs when the provider rejects it ([b39815d](https://github.com/Anyesh/wardrowbe/commit/b39815d52c666be445b6feb52d7f1f51abedefa3))
* surface real cause when outfit suggestion AI response is truncated ([#139](https://github.com/Anyesh/wardrowbe/issues/139)) ([#142](https://github.com/Anyesh/wardrowbe/issues/142)) ([7af8472](https://github.com/Anyesh/wardrowbe/commit/7af84720f1f6932d61fde8504edcf4b281f350fa))

## [1.5.1](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.5.0...wardrowbe-v1.5.1) (2026-07-17)


### 🐛 Bug Fixes

* [#124](https://github.com/Anyesh/wardrowbe/issues/124) fix prod compose file well ([3cded21](https://github.com/Anyesh/wardrowbe/commit/3cded21db36b877ef2a0a90815a620be2cc4bdf5))
* keep honoring NEXT_PUBLIC_API_URL when resolving the backend ([#124](https://github.com/Anyesh/wardrowbe/issues/124)) ([d8cca73](https://github.com/Anyesh/wardrowbe/commit/d8cca73dd5c20315e2d7d256b112663b84894c11))
* proxy /api/v1 through a route handler so BACKEND_URL applies ([#124](https://github.com/Anyesh/wardrowbe/issues/124)) ([2fff9c3](https://github.com/Anyesh/wardrowbe/commit/2fff9c399e0feae14266c36a1afb5ff46c437207))

## [1.5.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.4.0...wardrowbe-v1.5.0) (2026-07-16)


### ✨ Features

* add page-size control and scope select-all to current page ([#127](https://github.com/Anyesh/wardrowbe/issues/127)) ([7430a4f](https://github.com/Anyesh/wardrowbe/commit/7430a4f910a65d6db810a5381f362e91f902694f))
* allow bulk upload without forced AI analysis ([#128](https://github.com/Anyesh/wardrowbe/issues/128)) ([7984e26](https://github.com/Anyesh/wardrowbe/commit/7984e26f4fa233a1a40d95805e74e6444ffa2bc6))
* allow cancelling AI analysis on processing items ([#95](https://github.com/Anyesh/wardrowbe/issues/95)) ([05f3578](https://github.com/Anyesh/wardrowbe/commit/05f357808d55a74de1394b5ec36cf5472370ba21))
* support PUID/PGID overrides on app containers ([#123](https://github.com/Anyesh/wardrowbe/issues/123)) ([14674cb](https://github.com/Anyesh/wardrowbe/commit/14674cbbfd79e371b08d9761f02542aafe040cc3))
* undo background removal and replace primary image ([#126](https://github.com/Anyesh/wardrowbe/issues/126)) ([c1c10b2](https://github.com/Anyesh/wardrowbe/commit/c1c10b2803b90104d5323ef112e66f786af75baa))


### 🐛 Bug Fixes

* allow overriding backend URL for renamed compose services ([#124](https://github.com/Anyesh/wardrowbe/issues/124)) ([2a813d6](https://github.com/Anyesh/wardrowbe/commit/2a813d60d711aa31c45ae7c024f1389b345be170))
* chunk bulk uploads so batches over the limit no longer fail ([#125](https://github.com/Anyesh/wardrowbe/issues/125)) ([a4df578](https://github.com/Anyesh/wardrowbe/commit/a4df578b187b0343eff5091c49b7e02b76ec0546))

## [1.4.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.3.1...wardrowbe-v1.4.0) (2026-07-01)


### ✨ Features

* make internal AI optional and add capabilities endpoint ([#113](https://github.com/Anyesh/wardrowbe/issues/113)) ([376f9a6](https://github.com/Anyesh/wardrowbe/commit/376f9a6a1e846d3de7853f55ac76447f204c8529))


### 🐛 Bug Fixes

* add weather location fallbacks ([#75](https://github.com/Anyesh/wardrowbe/issues/75)) ([7426d6d](https://github.com/Anyesh/wardrowbe/commit/7426d6d8444769dd34263373ebf551ecaaf79b59))
* show config error on login when no auth provider is registered ([22e73ad](https://github.com/Anyesh/wardrowbe/commit/22e73ade5a9999fba2fb303a0533569d38294286))

## [1.3.1](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.3.0...wardrowbe-v1.3.1) (2026-06-26)


### 🐛 Bug Fixes

* make OIDC issuer URL trailing-slash agnostic ([#107](https://github.com/Anyesh/wardrowbe/issues/107)) ([152f175](https://github.com/Anyesh/wardrowbe/commit/152f17572488bb63bc5f65a0c1a3240752db12c1))
* OIDC issue [#114](https://github.com/Anyesh/wardrowbe/issues/114) ([7354232](https://github.com/Anyesh/wardrowbe/commit/73542322e0d56913d5e3f249f4679c05efd0eb74))


### 👷 CI/CD

* publish Docker images to GHCR on main and releases ([#83](https://github.com/Anyesh/wardrowbe/issues/83)) ([af22e84](https://github.com/Anyesh/wardrowbe/commit/af22e8410d37f04800dafa4cbc09a94e7fddd6bc))
* publish versioned images on release ([#112](https://github.com/Anyesh/wardrowbe/issues/112)) ([9677b39](https://github.com/Anyesh/wardrowbe/commit/9677b3918728355046d3d8f306b11b9a0d61bc6e))

## [1.3.0](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.2.4...wardrowbe-v1.3.0) (2026-05-31)


### ✨ Features

* add mobile callback [#58](https://github.com/Anyesh/wardrowbe/issues/58) ([44cf285](https://github.com/Anyesh/wardrowbe/commit/44cf285d3d612d1e1e97d1af110c284b716cb398))


### 🐛 Bug Fixes

* align .env.example SECRET_KEY with dev-mode sentinel ([a8f9f5e](https://github.com/Anyesh/wardrowbe/commit/a8f9f5e5a8c66da81084e49b18fa8c47f82e11ef)), closes [#72](https://github.com/Anyesh/wardrowbe/issues/72)
* Item pair score initialization for learning service ([9f7de07](https://github.com/Anyesh/wardrowbe/commit/9f7de07deb7216c55c2a091b481fc98be71d4ad2))
* select wardrobe items beyond the first page in studio ([c73c571](https://github.com/Anyesh/wardrowbe/commit/c73c5717ff23fd849154f5e44569d854400bb600))
* update cognitive cache thresh ([9170644](https://github.com/Anyesh/wardrowbe/commit/9170644a47140af7fb1e485c42af2688d9b95cde))
* update pair context for feedback without a rating ([3764dec](https://github.com/Anyesh/wardrowbe/commit/3764dec0c6462aad253bed6ea3bf4a834b31e2b7))


### 🔧 Maintenance

* add cognitive cache ([886e65f](https://github.com/Anyesh/wardrowbe/commit/886e65f43d5fa89365bb10f122a3066ce7b81551))
* **deps:** bump astral-sh/setup-uv from 4 to 7 ([84ceb98](https://github.com/Anyesh/wardrowbe/commit/84ceb98defc5c87b7322d4d26469d9fd65238e3f))
* **deps:** bump googleapis/release-please-action from 4 to 5 ([8a31d2c](https://github.com/Anyesh/wardrowbe/commit/8a31d2c379805284feb4e4d746d340262791b529))


### 👷 CI/CD

* install cognitive-cache via uv tool install ([6ede4f2](https://github.com/Anyesh/wardrowbe/commit/6ede4f237567de29c250936f4bc05ff6b896f99e))


### 📦 Build

* **deps:** bump codecov/codecov-action from 4 to 6 ([436997e](https://github.com/Anyesh/wardrowbe/commit/436997e8a4ff461a6336c442f6872da441dce1f7))

## [1.2.4](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.2.3...wardrowbe-v1.2.4) (2026-04-17)


### 🐛 Bug Fixes

* prevent same-slot item pairing, add socks/tie types, fix UI text… ([#55](https://github.com/Anyesh/wardrowbe/issues/55)) ([c457572](https://github.com/Anyesh/wardrowbe/commit/c4575720d706d30a432900693983b0a3b38fb1a8))
* refetch outfit after commit ([f9b3ceb](https://github.com/Anyesh/wardrowbe/commit/f9b3ceba0eab745682168151cee3adc112641afc))

## [1.2.3](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.2.2...wardrowbe-v1.2.3) (2026-03-30)


### 🐛 Bug Fixes

* use separate test database instead of falling back to production DB ([019d2e9](https://github.com/Anyesh/wardrowbe/commit/019d2e9b54a51c031b72281a2c4080d206a46b76))
* use separate test database instead of falling back to production DB ([7eae5c9](https://github.com/Anyesh/wardrowbe/commit/7eae5c9882e218908ef94fe0a1d413138df1f381))

## [1.2.2](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.2.1...wardrowbe-v1.2.2) (2026-03-20)


### 🐛 Bug Fixes

* 39: Add proper error messages for diagnose ([#40](https://github.com/Anyesh/wardrowbe/issues/40)) ([f4a71d1](https://github.com/Anyesh/wardrowbe/commit/f4a71d15eba68519f59ff571cca0a111d59cc0c7))
* enable dev credential login in Docker production builds ([#43](https://github.com/Anyesh/wardrowbe/issues/43)) ([9aab711](https://github.com/Anyesh/wardrowbe/commit/9aab71185d82a1a789a104abdbb842511285e001))

## [1.2.1](https://github.com/Anyesh/wardrowbe/compare/wardrowbe-v1.2.0...wardrowbe-v1.2.1) (2026-02-20)


### 🐛 Bug Fixes

* Add current user check ([84840ab](https://github.com/Anyesh/wardrowbe/commit/84840ab8da7727b24f127fa8d8ac18a57fbcbb51))
* Add missing test:coverage script to package.json ([43b8dfa](https://github.com/Anyesh/wardrowbe/commit/43b8dfa6a254c4af67e95b1bb3fefee2eac9d0e4))
* add missing URL fields to TypeScript interfaces ([6113dd6](https://github.com/Anyesh/wardrowbe/commit/6113dd6682227d82dc29251ed9a4fc9054047ad6))
* **ci:** Fix backend storage path and update Node.js to 20 ([55cda11](https://github.com/Anyesh/wardrowbe/commit/55cda11c76e03a490d3faa6981f50016bb1ebfde))
* Ensure opensource repo works for new users ([a003dbd](https://github.com/Anyesh/wardrowbe/commit/a003dbd1c65c8917148b00ac007b466fb6e3430a))
* modernize Python type annotations for Ruff linting ([208920b](https://github.com/Anyesh/wardrowbe/commit/208920bb1f60318100584fc12a1732154570461b))
* re-fetch items after update/archive/restore to load relationships ([edfa65c](https://github.com/Anyesh/wardrowbe/commit/edfa65ce5d9516f61b6094554886f7aec0d452f2))
* Resolve all CI quality check failures ([2209cdf](https://github.com/Anyesh/wardrowbe/commit/2209cdf66ff86090b95e583a6d587be429c2b357))
* resolve CI lint/type/test failures from v1.2.0 release ([3568174](https://github.com/Anyesh/wardrowbe/commit/35681741610d8f696665b63ffc2ee15ad6c94fea))
* Resolve lint and format issues ([86799df](https://github.com/Anyesh/wardrowbe/commit/86799df4e116e3ab3ee4fde4da64e9b945263dac))
* Update AccumulatedItem types to match Item interface ([3e85320](https://github.com/Anyesh/wardrowbe/commit/3e853208a9b2abd99489415d77c923216825689a))


### 📝 Documentation

* improve setup instructions and fix dev mode ([3b567de](https://github.com/Anyesh/wardrowbe/commit/3b567de06f49c5fbe04bfbc04c58ccbf3d743d69))


### 🔧 Maintenance

* add git-blame-ignore-revs for formatting commits ([38fcc6f](https://github.com/Anyesh/wardrowbe/commit/38fcc6f210089bfd0e2bb7979fbfc26487974ba5))
* Add pre-commit hooks for lint/format enforcement ([90343d3](https://github.com/Anyesh/wardrowbe/commit/90343d39fbfd413bf6bbce273d7c7d5b205ba2cc))
* Add tsbuildinfo to gitignore ([b5280aa](https://github.com/Anyesh/wardrowbe/commit/b5280aa158a3eb9228e712444ec62fef918b094e))
* fix linting errors and add missing type properties ([f1c4848](https://github.com/Anyesh/wardrowbe/commit/f1c484883d766961410977de1a81837679a8630f))
* **release:** Add example screens ([2add224](https://github.com/Anyesh/wardrowbe/commit/2add2242a1342de29777fcb4ae74068bb6c8aab1))


### 💄 Styling

* Update README badges to for-the-badge style ([#10](https://github.com/Anyesh/wardrowbe/issues/10)) ([6eff9e9](https://github.com/Anyesh/wardrowbe/commit/6eff9e9278a424ff49e1a9b1d93b5611eb05e123))

## [Unreleased]

### Added

### Changed

### Fixed

## [1.2.0] - 2026-02-06

### Added
- **Wash Tracking** — Track when items need washing based on wear count
  - Per-item configurable wash intervals (or smart defaults by clothing type, e.g. jeans every 6 wears, t-shirts every wear)
  - Visual wash status indicator with progress bar in item detail
  - "Mark as Washed" button to reset the counter
  - Full wash history log with method and notes
  - `needs_wash` filter in the wardrobe to quickly find dirty clothes
  - Background worker sends consolidated laundry reminder notifications every 6 hours via ntfy
- **Multi-Image Support** — Upload up to 4 additional photos per clothing item
  - Image gallery with carousel navigation in item detail dialog
  - Thumbnail strip for quick image switching
  - Set any additional image as the new primary image (swaps them)
  - Add/delete additional images while editing
- **Family Outfit Ratings** — Rate and comment on family members' outfits
  - Star rating (1–5) with optional comment
  - Family Feed page to browse other members' outfits and leave ratings
  - Ratings displayed on outfit history cards and preview dialogs
  - Average family rating shown on outfit cards
  - Family Feed link added to sidebar, mobile nav, and dashboard
- **Wear Statistics** — Detailed per-item wear analytics
  - Total wears, days since last worn, average wears per month
  - Wear-by-month mini bar chart (last 6 months)
  - Wear-by-day-of-week breakdown
  - Most common occasion detection
  - Wear timeline with outfit context (which items were worn together)
- **Wardrobe Sorting & Filtering** — More control over how items are displayed
  - Sort by: newest, oldest, recently worn, least recently worn, most/least worn, name A–Z/Z–A
  - Filter by: needs wash, favorites
  - Collapsible filter bar with active filter count badge
  - "Clear filters" button
- **Improved Item Navigation** — Click items in outfit views to jump to item detail
  - Outfit suggestion items link to wardrobe detail
  - Outfit preview dialog items link to wardrobe detail
  - History card "wore instead" preview links to item detail
  - Deep-link support via `?item=<id>` URL parameter
- **Smarter AI Recommendations** — AI avoids suggesting items that need washing and recently worn exact outfit combinations
- Signed image URLs for improved security

### Changed
- Wear history endpoint now includes full outfit context (which items were worn together)
- "Wore instead" items now also update wash tracking counters
- Item detail dialog redesigned with image gallery, wash status section, and wear history section
- Forward auth token validation made more lenient (`iat` now optional)

### Fixed
- Ruff linting errors in auth.py and images.py
- AccumulatedItem types to match Item interface
- Analytics page item cards now use signed `thumbnail_url` instead of raw path
- Token decode error handling improved with catch-all for malformed payloads

## [1.1.0] - 2026-01-30

### Added
- **AI Learning System** - Netflix/Spotify-style recommendation learning that improves over time
  - Learns color preferences from user feedback patterns
  - Tracks item pair compatibility scores based on outfit acceptance
  - Builds user learning profiles with computed style insights
  - Generates actionable style recommendations
- **"Wore Instead" Tracking** - Record what you actually wore when rejecting suggestions to improve future recommendations
- **Learning Insights Dashboard** - View your learned preferences, best item pairs, and AI-generated style insights
- **Outfit Performance Tracking** - Detailed metrics on outfit acceptance rates, ratings, and comfort scores
- Pre-commit hooks for lint/format enforcement

### Fixed
- Backend storage path and updated Node.js to 20
- Added missing test:coverage script to package.json
- Ensure opensource repo works for new users
- Resolved all CI quality check failures

## [1.0.0] - 2026-01-25

### Added
- **Photo-based wardrobe management** - Upload photos with automatic AI-powered clothing analysis
- **Smart outfit recommendations** - AI-generated suggestions based on weather, occasion, and preferences
- **Scheduled notifications** - Daily outfit suggestions via ntfy, Mattermost, or email
- **Family support** - Manage wardrobes for multiple household members
- **Wear tracking** - History, ratings, and outfit feedback system
- **Analytics dashboard** - Visualize wardrobe usage, color distribution, and wearing patterns
- **Outfit calendar** - View and track outfit history by date
- **Pairing system** - AI-generated clothing pairings with feedback learning
- **User preferences** - Customizable style preferences and notification settings
- **Authentication** - Secure user authentication with session management
- **Health checks** - API health monitoring endpoints
- **Docker support** - Full containerization with docker-compose for dev and production
- **Kubernetes manifests** - Production-ready k8s deployment configurations
- **Database migrations** - Alembic-based schema migrations
- **Test suite** - Comprehensive backend and frontend tests

### Technical
- Backend: FastAPI with Python
- Frontend: Next.js with TypeScript
- Database: PostgreSQL with Redis caching
- AI: Compatible with OpenAI, Ollama, LocalAI, or any OpenAI-compatible API
- Reverse proxy: Nginx/Caddy configurations included

[Unreleased]: https://github.com/username/wardrowbe/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/username/wardrowbe/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/username/wardrowbe/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/username/wardrowbe/releases/tag/v1.0.0
