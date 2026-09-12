# E-mail: omschakelen naar no-reply@mail.gsprecruitment.nl

Draaiboek voor de eigenaar. Dit document neemt niets aan over voorkennis
van DNS of Google Workspace-beheer; elke stap benoemt waar je moet zijn en
wat je daar invult.

Alle DNS-commando's in dit document draaien vanaf je eigen laptop, niet op
de VPS. Alle `.env`-wijzigingen aan het eind gebeuren op de VPS via
`talent-os/.env` (zie docs/BACKUP-RESTORE.md voor hoe je op de VPS
inlogt).

## 1. Doel

Automatische mail (verificatie, wachtwoordreset, talentpool-bevestiging en
-herinnering, eigenaarsmeldingen) vertrekt straks van
`no-reply@mail.gsprecruitment.nl` in plaats van `info@gsprecruitment.nl`,
met `Reply-To: info@gsprecruitment.nl` zodat een antwoord alsnog bij het
hoofdadres binnenkomt.

Waarom een apart subdomein: als er ooit een mail bounct, als spam wordt
gemarkeerd of een verkeerde ontvanger krijgt, raakt dat de reputatie van
`mail.gsprecruitment.nl`, niet van het hoofddomein `gsprecruitment.nl`.
Het hoofddomein (en dus `info@`) houdt zijn eigen SPF/DKIM/DMARC en blijft
buiten deze wijziging.

## 2. Google Workspace: het subdomein toevoegen

Deze stap gebeurt in de Workspace-beheerconsole
(admin.google.com), niet in Cloudflare.

1. **Domeinalias toevoegen.** Beheerconsole → Account → Domeinen →
   Domeinen beheren → Domeinalias toevoegen → `mail.gsprecruitment.nl`.
   Google vraagt om het domein te verifiëren (meestal via een TXT-record
   dat Google je op dat moment toont -- zet dat record in Cloudflare zoals
   Google het voorschrijft, dat record staat los van de records in
   stap 3 hieronder).

2. **DKIM genereren.** Beheerconsole → Apps → Google Workspace → Gmail →
   E-mail authenticeren. Kies daar het domein `mail.gsprecruitment.nl`
   (niet het hoofddomein -- dat heeft al een eigen DKIM-sleutel, zie
   stap 3), sleutelgrootte **2048 bits**, en klik op genereren. Google
   toont dan een hostnaam (de selector, bijvoorbeeld `google._domainkey`
   of een datumselector als `google2026`) en een lange TXT-waarde.
   **Noteer de exacte selectornaam** -- die heb je in stap 3 nodig, en hij
   verschilt vaak van het hoofddomein.

3. **Het adres zelf: alias of apart account.** Er zijn twee routes, en ze
   werken niet voor dezelfde verzendweg:

   - **Alias op een bestaand account** (bijvoorbeeld op het account dat
     nu `info@` beheert). Voor de **Gmail API** (de huidige verzendweg,
     `EMAIL_PROVIDER=gmail`) is dit verplicht: verzenden namens een alias
     via de Gmail API vereist dat het account waarvan de OAuth-token
     draait, die alias heeft ingesteld onder Gmail-instellingen → Accounts
     → "Mail verzenden als" (met "Behandelen als alias" aangevinkt). Zonder
     die stap negeert Gmail het gevraagde afzenderadres of weigert de
     send-aanroep.
   - **Apart account** (`no-reply@mail.gsprecruitment.nl` als eigen
     Workspace-gebruiker, met eigen OAuth-toestemming of eigen SMTP-relay-
     credentials). Nodig voor **SMTP-relay** (stap hieronder) als je dat
     los van het bestaande Gmail API-account wilt draaien, en de
     eenvoudigste route als je wilt vermijden dat het account achter
     `info@` iets met het subdomein te maken heeft.

   Kies er één; noteer die keuze hieronder in je eigen kopie van dit
   document, want stap 5 verwijst ernaar.

   **SMTP-relay** (nodig als je later `EMAIL_PROVIDER=smtp` kiest in
   plaats van de Gmail API): Google Workspace biedt hiervoor
   `smtp-relay.google.com` op poort 587 met STARTTLS. In de
   beheerconsole: Apps → Google Workspace → Gmail → SMTP-relaydienst controle
   toevoegen; je kiest daar tussen "alleen geregistreerde apparaten" (op
   IP-adres van de VPS) of "vereis SMTP-authenticatie" (met een
   accountwachtwoord of app-wachtwoord -- vereist dat 2FA op dat account
   dan met een app-wachtwoord werkt in plaats van alleen OAuth). Voor een
   VPS met een vast IP is de IP-route eenvoudiger en past bij
   `SMTP_USER`/`SMTP_PASS` leeg te laten; voor authenticatie vul je die
   twee variabelen wel in.

## 3. DNS in Cloudflare

Log in op het Cloudflare-dashboard voor `gsprecruitment.nl` → DNS →
Records. Elk record hieronder moet op **"DNS only"** staan (het grijze-
wolk-icoon, niet oranje/proxied) -- een TXT-record voor e-mailauthenticatie
mag nooit door Cloudflare's proxy gaan.

| Type | Naam | Waarde |
|---|---|---|
| TXT | `mail.gsprecruitment.nl` | `v=spf1 include:_spf.google.com ~all` |
| CNAME of TXT | `<selector>._domainkey.mail.gsprecruitment.nl` | de waarde die Google in stap 2 toonde |
| TXT | `_dmarc.mail.gsprecruitment.nl` | eerst `v=DMARC1; p=quarantine; rua=mailto:<eigen-adres>` |

Zet `_dmarc.mail.gsprecruitment.nl` pas op `p=reject` nadat stap 4
hieronder een aantal dagen achtereen PASS heeft laten zien op alle drie
de checks -- `p=reject` direct vanaf dag één betekent dat een fout in
stap 2 of 3 mail stil laat verdwijnen in plaats van in het spamvak.

Voor `_dmarc.gsprecruitment.nl` (het **root**-domein, niet het
subdomein) schrijft het oorspronkelijke plan voor: eerst `p=none` met
alleen rapportage, als er nog geen DMARC op het rootdomein staat.

**Vastgesteld op 2026-09-10** (opgevraagd via `cloudflare-dns.com/dns-
query`, zie commando's hieronder): dat is hier niet van toepassing -- het
rootdomein heeft al langer een eigen DMARC-record, en dat staat al op
`p=quarantine`, niet op `p=none`:

```
gsprecruitment.nl            TXT   v=spf1 include:_spf.google.com ~all
_dmarc.gsprecruitment.nl     TXT   v=DMARC1; p=quarantine; pct=100; rua=mailto:dmarc-reports@gsprecruitment.nl; aspf=r; adkim=r
mail.gsprecruitment.nl       TXT   (bestaat nog niet -- NXDOMAIN)
_dmarc.mail.gsprecruitment.nl TXT  (bestaat nog niet -- NXDOMAIN)
```

Ook al aanwezig, ter info (niet iets om in deze stap te wijzigen): MX
naar Google (`aspmx.l.google.com` e.a.) en een DKIM-record op het
rootdomein onder de selector `google._domainkey.gsprecruitment.nl`. Dat
bevestigt dat Workspace voor het hoofddomein al draait; deze stap voegt
alleen het subdomein `mail.gsprecruitment.nl` ernaast toe, met zijn eigen
selector uit stap 2 -- gebruik die niet opnieuw voor het subdomein, Google
geeft per domeinalias doorgaans een eigen selectornaam.

Conclusie voor dit spoor: het rootdomein hoeft niet aangepast te worden
(het staat al op `p=quarantine`, strenger dan het `p=none`-startpunt uit
het oorspronkelijke plan); alleen de drie subdomeinrecords in de tabel
hierboven zijn nieuw. Geen aparte Google-verificatie-TXT nodig: de
aanwezige MX- en DKIM-records op het rootdomein tonen dat Workspace daar
al geverifieerd draait, en dat dekt het subdomein mee.

Zelf opnieuw controleren nadat je de records hebt gezet:

```bash
dig TXT gsprecruitment.nl +short
dig TXT _dmarc.gsprecruitment.nl +short
dig TXT mail.gsprecruitment.nl +short
dig TXT _dmarc.mail.gsprecruitment.nl +short
```

Werkt `dig` niet (bijvoorbeeld op macOS zonder extra tools, of vanaf een
machine zonder DNS-utilities), gebruik dan een van deze twee alternatieven
en noteer de uitkomst letterlijk in je eigen kopie van dit document:

```bash
python3 -c "
import dns.resolver
for name in ['gsprecruitment.nl', '_dmarc.gsprecruitment.nl', 'mail.gsprecruitment.nl', '_dmarc.mail.gsprecruitment.nl']:
    try:
        for r in dns.resolver.resolve(name, 'TXT'):
            print(name, r)
    except Exception as e:
        print(name, 'geen record:', e)
"
```

```bash
curl -s "https://cloudflare-dns.com/dns-query?name=mail.gsprecruitment.nl&type=TXT" -H "accept: application/dns-json"
```

DNS-propagatie kan tot enkele uren duren (TTL-afhankelijk); een record dat
net gezet is en nog niet terugkomt, is meestal een kwestie van wachten,
geen fout in de instelling.

## 4. Verificatie

Stuur, zodra `EMAIL_PROVIDER`/`EMAIL_FROM` zijn omgezet (stap 5) en er
minstens één test-mail is verstuurd, die mail naar een gewoon Gmail-adres.
Open hem in Gmail, klik rechtsboven op de drie puntjes → **Origineel
weergeven**. Daar moeten alle drie deze regels op PASS staan:

- **SPF**: `PASS` met `mail.gsprecruitment.nl` als de domeinnaam die
  gecontroleerd is.
- **DKIM**: `PASS` met `d=mail.gsprecruitment.nl` (niet het rootdomein --
  als hier het rootdomein staat, is de DKIM-configuratie in stap 2 niet
  op het juiste domein toegepast).
- **DMARC**: `PASS`.

Als één ervan faalt:

- **SPF FAIL**: het TXT-record in stap 3 ontbreekt, staat nog niet
  gepropageerd, of staat per ongeluk op "Proxied" (oranje wolk) in
  Cloudflare -- zet op "DNS only".
- **DKIM FAIL of geen DKIM-handtekening**: de selector in stap 3 komt
  niet overeen met de selector die Google in stap 2 toonde, of de
  DKIM-sleutel in de Workspace-beheerconsole staat nog niet op
  "geactiveerd" (na het genereren moet je hem in dezelfde
  beheerconsole-pagina apart activeren).
- **DMARC FAIL** terwijl SPF en DKIM beide PASS zijn: controleer `aspf`/
  `adkim` alignment -- bij de strikte instelling (`s`) moet het
  `From`-domein exact gelijk zijn aan het SPF- of DKIM-domein; met de
  relaxed-default (`r`, zoals hierboven) volstaat een subdomeinmatch, dus
  dit zou met de records in stap 3 niet moeten optreden.

Herhaal de test pas als het gerapporteerde record ook echt terugkomt in
de `dig`/curl-controle uit stap 3 -- een test vóór propagatie geeft een
fout die niets zegt over de configuratie zelf.

## 5. Omschakelen in `.env`

Op de VPS, in `talent-os/.env`:

```
EMAIL_FROM=GSP Recruitment <no-reply@mail.gsprecruitment.nl>
```

Alleen bij SMTP-relay (stap 2) in plaats van de Gmail API, ook:

```
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp-relay.google.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
```

(`SMTP_USER`/`SMTP_PASS` leeg laten bij de IP-geautoriseerde relay-optie
uit stap 2; invullen bij de authenticatie-optie.)

Herstart de backend zodat de nieuwe waarden geladen worden:

```bash
ssh gsp@188.245.254.248
cd /home/gsp/projects/gsp-recruitment
docker compose restart backend
```

Rollback (terug naar het huidige, werkende adres):

```
EMAIL_PROVIDER=gmail
EMAIL_FROM=GSP Recruitment <info@gsprecruitment.nl>
```

gevolgd door dezelfde `docker compose restart backend`. Dit raakt geen
code of database aan -- puur twee env-variabelen, dus zonder risico op
dataverlies.

## 6. Uitwijk bij volume (beslispunt, niet gekozen in dit spoor)

Als het verzendvolume ooit boven wat Gmail/Workspace als transactionele
afzender comfortabel verwerkt uitkomt, is de kleinste vervolgstap een
EU-gevestigde transactionele e-mailverzender aangesloten via diezelfde
`SmtpProvider` (STARTTLS, poort 587) in `services/email_service.py` --
geen nieuwe providerklasse nodig, alleen andere `SMTP_*`-waarden en
`EMAIL_PROVIDER=smtp`.

Dat vereist wel, vóór het eerste bericht daar doorheen gaat: een rij in
`docs/VERWERKINGSREGISTER.md` §1.3 (nieuwe verwerker, categorieën
verwerkte gegevens, doorgifte) en een verwerkersovereenkomst met die
partij. Dat is een eigen beslissing met een eigen leverancierskeuze -- dit
document kiest niet welke partij dat wordt, het benoemt alleen dat de
technische kant al aansluit.

## 7. Meldingen aan de eigenaar

`OWNER_NOTIFY_EMAIL` (in `talent-os/.env`) is de mailbox waar
`services/notify.py` een interne melding naartoe stuurt bij een nieuwe
registratie, Google-aanmelding, lead of talentpool-bevestiging -- naast de
Telegram-melding die al bestaat en ongewijzigd blijft (geen naam of
e-mailadres daarin).

Zet dit op een eigen mailbox (bijvoorbeeld een aparte Workspace-gebruiker
of een label/filter binnen een bestaande inbox), niet noodzakelijk op
`info@` zelf: `info@` is het publieke, klantgerichte adres waar reacties
op binnenkomen -- interne systeemmeldingen (elke nieuwe registratie, elke
Google-aanmelding) lopen op enig volume snel op en verdringen dan de
mails die wél direct beantwoord moeten worden. Een apart adres houdt die
twee stromen leesbaar gescheiden.

Leeg laten (de default) betekent: geen eigenaarsmail, alleen de bestaande
Telegram-melding.

## 8. Eigenaarsactie: WAF-uitzondering voor het een-klik-afmelden

**Nog te doen, door de eigenaar, in het Cloudflare-dashboard. Deze
reparatieronde heeft niets aan de WAF veranderd.**

Elke job-alert draagt twee RFC 8058-headers:

```
List-Unsubscribe: <https://api.gsprecruitment.nl/api/public/unsubscribe?token=...&scope=alerts>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

Klikt iemand in Gmail of Outlook op "Afmelden", dan POST'et de
MAILPROVIDER naar die URL -- niet de browser van de ontvanger, en niet
onze eigen frontend. Die POST draagt de header `User-Agent: gsp-ops`
dus niet: de provider stuurt zijn eigen user-agent en er is geen plek waar
wij daar iets aan kunnen toevoegen. De WAF-regel die bare curl 403't
(zie `CLAUDE.md`, "API facts that bite") blokkeert die POST daarmee ook.

Het gevolg is onzichtbaar en precies de verkeerde kant op: het
afmeldendpoint antwoordt met opzet altijd hetzelfde generieke bericht, een
provider probeert zo'n POST niet opnieuw, en de ontvanger ziet in zijn
mailclient "je bent afgemeld" terwijl er niets is gebeurd. Morgen krijgt
hij dezelfde digest.

Nodig is dus één uitzondering, zo smal mogelijk:

- alleen `POST`;
- alleen het pad `/api/public/unsubscribe` op `api.gsprecruitment.nl`;
- alleen de user-agent-eis eraf, niet de overige WAF-bescherming.

Wat aan onze kant al is geregeld, zodat die uitzondering niets opent wat
dicht hoorde te blijven: het endpoint heeft geen authenticatie om te
omzeilen, doet niets zonder een geldig token van 32 random bytes, verbruikt
dat token bij de eerste aanroep (`job_alert_sends.used_at`) en laat het na
90 dagen verlopen.

En het token in die URL is niet hetzelfde token als in de zichtbare
afmeldlink. Elke verzending draagt er twee, met twee aparte hashes op
dezelfde `job_alert_sends`-rij. Het token in de `List-Unsubscribe`-URL
hierboven levert ALTIJD `scope=alerts` op: `routers/public.py
unsubscribe()` zoekt eerst op `oneclick_token_hash`, en een treffer daar
betekent `alerts`, ongeacht wat de body, de querystring of een opgegeven
scope zegt. `scope=all` (toestemming intrekken plus blokkeerlijst,
onomkeerbaar) is uitsluitend bereikbaar met het ANDERE token, dat in het
fragment van de voettekstlink staat en dus in geen enkele log terechtkomt.
Wie de URL hierboven uit een logregel plukt en het token in de body plakt,
komt daarmee niet verder dan een afmelding voor vacature-alerts.
Daarbovenop geldt onveranderd dat een token in de querystring nooit meer
dan `alerts` oplevert, ook het fragmenttoken niet.

De rate limit op dit pad staat op 60/minuut, ruim genoeg voor de gedeelde
uitgaande IP-adressen van een mailprovider.

Tot die uitzondering er is, werkt het afmelden via de zichtbare link in de
voettekst van het bericht wél: die gaat langs de website en de gewone
browser van de ontvanger.

## 9. Deployvolgorde: eerst migreren, dan de nieuwe code live zetten

`.github/workflows/deploy.yml` bouwde tot deze reparatieronde eerst de
nieuwe backend en startte hem ook meteen (`docker compose up -d --build
backend`), en draaide de migraties pas in de stap daarna. Tussen die twee
stappen draaide de nieuwe code dus op het oude schema.

Dat is niet theoretisch. `core/retention.py`'s `LOGIN_STAMP_SQL` schrijft
`users.dormant_warning_attempts` en `users.dormant_warning_attempt_at`
(migratie 042) en wordt in alle vier de inlogpaden aangeroepen
(`routers/auth.py` wachtwoord en Google, `routers/mfa.py` twee
tweede-factorstappen), zonder try/except. Bestaan die kolommen nog niet,
dan geeft élke login in dat venster een 500 (`UndefinedColumnError`) --
ook die van de beheerder, die daarmee net dan niet bij het adminpaneel
kan. Hetzelfde geldt voor elke toekomstige migratie: dit is een
eigenschap van de volgorde, niet van dit spoor.

De stappen staan daarom nu zo:

1. **Build the new backend image and make sure postgres is up** --
   `docker compose build backend` bouwt en tagt dezelfde image die `up
   --build` tagde, maar vervangt de draaiende container niet.
   `docker compose up -d --wait postgres` start postgres expliciet: de
   migratiestap gebruikt `--no-deps` en kreeg die afhankelijkheid tot nu
   toe stilzwijgend van de `up -d --build backend` die hier stond.
2. **Run database migrations** -- inhoudelijk onveranderd: nog steeds
   `docker compose run --rm -T --no-deps backend` over `migrations/0*.py`
   in bestandsnaamvolgorde, op de zojuist gebouwde image, met dezelfde
   `env_file`-regels en dus dezelfde database-URL als de service zelf.
   Alleen de plaats in de volgorde is veranderd.
3. **Start the new backend image** -- `docker compose up -d backend`.
   Pas hier gaat de nieuwe code live, op een schema dat er al bij past.

Mislukt stap 2, dan draait de oude backend nog gewoon: er is dan niets
omgeschakeld en de rollback-tak onderaan het bestand (image `:previous`
terugtaggen) doet wat hij altijd deed.
