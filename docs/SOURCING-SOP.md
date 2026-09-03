# Sourcing SOP — kandidaten en prospects werven zonder Apollo

Status: verplicht voor iedere mens en iedere routine die kandidaten of klantprospects opzoekt of benadert (`gsp-candidate-scout`, `gsp-match-and-draft`, `gsp-draft-qa`, `gsp-client-leads`). Apollo-jobs worden in M0-PR WS-C.3a (#16) standaard uitgezet; tot die merge geldt de `system_settings`-schakelaar en besluit §5.7. Router en key worden pas in WS-E.8 verwijderd; de bestaande pool valt eveneens onder besluit §5.7. Deze SOP vervangt geen ander proces, hij is het proces. Vastgesteld: growth-marketer → security-auditor → chief-of-staff (WS-F.4).

GSP is faceless: wij benaderen mensen als bedrijf ("wij"), nooit als privépersoon. Register is NRC/FD: plain, direct, geen hype, geen verzonnen cijfers of valse urgentie — ook niet in een openingsbericht.

---

## 1. Toegestane kanalen en werkwijze per kanaal

Alleen de kanalen hieronder zijn toegestaan. Alles daarbuiten is verboden totdat deze SOP is bijgewerkt.

### 1.1 LinkedIn — native zoeken, handmatige beoordeling
- Zoeken en profielen bekijken uitsluitend via de gewone LinkedIn-zoekfunctie en het gewone webscherm, door een mens. Zoeken is en blijft mensenwerk; er bestaat onder deze SOP geen goedgekeurde vorm van geautomatiseerd LinkedIn-zoeken.
- Geen automatiseringstools, geen browserextensies die profielen scrapen of exporteren, geen bulk-export van zoekresultaten of connecties.
- Geen geautomatiseerde connectieverzoeken, geen geautomatiseerde InMail/berichten, geen bots die profielbezoeken simuleren. Dit volgt uit de LinkedIn User Agreement, sectie "Dos and Don'ts": leden mogen onder meer geen software gebruiken om gegevens te verzamelen ("scrape or copy profiles and information of others"), geen geautomatiseerde middelen gebruiken om in te loggen of te navigeren, en LinkedIn niet gebruiken voor "spamming" of ongevraagde bulkcontact ([linkedin.com/legal/user-agreement](https://www.linkedin.com/legal/user-agreement)).
- Richtsnoer: 5-10 profielen per week per openstaande rol, handmatig beoordeeld (WS-F.5(2)).
- Bedrijfspagina 2×/week posten (vacatures, hergebruikte blogposts) is wel toegestaan — dat is publiceren, geen geautomatiseerd verzamelen.

### 1.2 GitHub — signaalsourcing
- Zoeken naar actieve contributors van relevante open-source projecten (Zephyr, FreeRTOS, PX4, Yocto, ROS2 en vergelijkbare embedded/OT-projecten) via de gewone GitHub-zoekfunctie, door een mens die de resultaten handmatig doorloopt. Geautomatiseerd doorzoeken van GitHub (bijv. bulk-gebruik van de API buiten normaal, laag-volume zoekgedrag) is onder deze SOP niet toegestaan en vereist eerst een apart eigenaarsbesluit én een nieuwe LIA-paragraaf (WS-E.11) vóórdat het mag starten.
- **Contact alleen via het kanaal dat de persoon zelf publiceert voor contact** — bijvoorbeeld een LinkedIn-link of portfolio-URL in het GitHub-profiel. Nooit automatisch, altijd door een mens beoordeeld.
- **Nooit e-mailadressen gebruiken die uit commits, commit-metadata of profielen zijn gehaald**, ook niet als het adres publiek zichtbaar is in een diff. Dit volgt uit de GitHub Acceptable Use Policies, die het verzamelen ("scraping") van gebruikersgegevens voor ongevraagd contact expliciet verbiedt: "You may not access or search... any part of the Service... through the use of any... scraping... except as permitted by the GitHub API Terms of Service" en het gebruik van GitHub-data voor spam/ongevraagde commerciële communicatie ([docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies)).
- Geen scraping-tools, geen bulk API-crawls buiten normaal, laag-volume, handmatig zoekgedrag.

### 1.3 Referrals
- Alleen ná de eerste plaatsing (er is dan pas een referral-basis) — niet eerder.
- Altijd toestemming van de aangedragen persoon vóór het eerste contact; herkomst wordt geregistreerd als "referrer" plus de naam van de verwijzende relatie (intern, niet gepubliceerd); `lawful_basis` = `toestemming_referral`.
- Een referral-bonus wordt alleen uitgekeerd na een expliciet eigenaarsbesluit; de GDPR-behandeling van de aangedragen persoon volgt dezelfde regels als elke andere kandidaat (§2 en §6).

### 1.4 Eigen portalregistraties
- Iedereen die zich zelf registreert op het kandidatenportal of via een formulier op de site is de herkomst zelf; geen aparte sourcing-actie nodig. In de code wordt dit vastgelegd als `source='portal_registration'`, zonder `source_url` — eigen registratie is een eigen, aparte grondslag (`lawful_basis` = `portal_registratie`) en valt buiten de "geen `source_url` = geen contact"-regel van §2, omdat de persoon zelf het eerste contact heeft gelegd.

### 1.5 Opt-in talentpool (WS-C.17)
- Alleen mensen met een geldig, ingevuld talentpool-vinkje (`consent_talentpool_at` gezet, `consent_talentpool_until` niet verstreken) mogen actief benaderd worden op basis van die toestemming.
- Verlopen of ingetrokken toestemming = direct geen contact meer op deze grondslag.
- Zelfde uitzondering als §1.4: herkomst is de eigen site (het vinkje zelf), dus `source_url` is niet vereist voor talentpool-contact — de grondslag is `opt_in_talentpool`, niet een gesourcete `source_url`.

### 1.6 Meetups en community's
- Fysieke of online aanwezigheid bij 040coders, Bits&Chips Event, DSPE, ICS-security-meetup (Amsterdam Cyber Security for Control Systems) en vergelijkbare vakcommunity's.
- Contact dat daar ontstaat, wordt behandeld als een normale eerstecontact-situatie (§2, §3): ook een gesprek op een meetup vervangt geen logregel.

### 1.7 TU/e en Fontys — gratis contactmomenten
- Alleen de gratis touchpoints (bijv. TU/e partner career support zonder premium-abonnement). Betaalde premium-diensten (zoals TU/e Technificent) zijn afgewezen (WS-F.10, §5.4).

### 1.8 Holland Expat Center South
- Voor de internationale/AAE-lijn: gratis touchpoints en verwijzingen via Holland Expat Center South en vergelijkbare expat-community's.

### 1.9 Brainport-vacatureportaal
- Pas beschikbaar ná WS-A.5 (demo-vacatures verborgen) en WS-A.6 (portaal-registratie): de Textkernel-spider indexeert alleen echte vacatures. Tot die voorwaarden zijn afgerond, blijft dit kanaal uit.

### 1.10 Uitdrukkelijk verboden
- Apollo.io, PhantomBuster, LinkedIn-scraping-extensies, of enige vergelijkbare geautomatiseerde verzameltool.
- Bulk e-mailfinders (Hunter, Snov, RocketReach en vergelijkbaar).
- Gekochte of gehuurde adreslijsten, ongeacht bron.
- Contact met privéadressen van natuurlijke personen zonder een vastgelegde grondslag (opt-in, bestaande relatie, of eigen publicatie van het adres als zakelijk contactpunt).
- Elke vorm van geautomatiseerd bulkbericht (LinkedIn, e-mail of anderszins) — outreach is en blijft draft-only, een mens verstuurt.

Reden, kort: de Autoriteit Persoonsgegevens noemt scraping door private partijen voor commerciële doeleinden in de handreiking van 2024 "bijna altijd onrechtmatig" ([autoriteitpersoonsgegevens.nl/documenten/handreiking-scraping-door-particulieren-en-private-organisaties](https://www.autoriteitpersoonsgegevens.nl/documenten/handreiking-scraping-door-particulieren-en-private-organisaties)).

---

## 2. Verplichte logvelden per persoon — vóór elk contact

Elke persoon (kandidaat of prospect-contactpersoon) die via sourcing wordt gevonden, krijgt vóór het eerste contactmoment onderstaande velden ingevuld. Dit geldt voor mensen én voor routines (`gsp-candidate-scout` schrijft deze velden weg; `gsp-match-and-draft` en `gsp-draft-qa` lezen ze uit vóór een draft wordt gemaakt of goedgekeurd).

| Veld | Verplicht | Toelichting |
|---|---|---|
| `source_url` | Ja, altijd | Publieke `http(s)`-URL waar de persoon zelf is gevonden (LinkedIn-profiel, GitHub-profiel, portfolio, carrièrepagina). Geen `source_url` = geen contact. |
| `date_found` | Ja | Datum waarop de persoon is gevonden; startpunt voor de bewaartermijn (§6). |
| `lawful_basis` | Ja | Voor kandidaten, één vaste waardenset: `gerechtvaardigd_belang` (LinkedIn/GitHub/meetup), `opt_in_talentpool` (WS-C.17), `toestemming_referral` (§1.3), `portal_registratie` (§1.4). Voor prospects, de WS-E.7-set: `zakelijk_functioneel_adres`, `opt_in`, of `bestaande_relatie`. |
| `consent_talentpool_at` / `consent_scope` | Alleen bij talentpool-kanaal | Moet gezet en niet verlopen zijn (WS-C.17). |
| `consent_spec_presentation_at` | Alleen vóór anonieme presentatie aan een klant | Zie §5 — apart van toestemming voor eerste contact. |
| `opt_out` / `consent_withdrawn_at` | Controleren bij elk vervolgcontact | Aanwezig = stop, geen uitzondering. |
| suppressielijst-check | Ja, bij elk bericht | Persoon mag niet op de suppressielijst staan (§3, STOP-afhandeling). |

Tot WS-E.7/C.17 deze velden als eigen databasekolommen oplevert, worden ze in het notitieveld van het record vastgelegd in exact deze sleutel=waarde-vorm, één per regel: `source_url=`, `date_found=`, `lawful_basis=`, `consent_talentpool_at=`, `consent_talentpool_until=`, `consent_spec_presentation_at=`, `opt_out=`, `consent_withdrawn_at=`. `gsp-candidate-scout` en `gsp-draft-qa` lezen en schrijven deze sleutels totdat de kolommen bestaan.

**Regel: geen herkomst-URL = geen contact** (behalve eigen portalregistraties, §1.4, en opt-in talentpool, §1.5 — in beide gevallen heeft de persoon zelf de relatie gelegd). Dit geldt zonder uitzondering voor gesourcete personen, ook wanneer een naam of e-mailadres op een andere manier bekend is geworden (bijv. via een collega of een oud bestand). Zonder `source_url` wordt niemand gesourcet benaderd en wordt niemand in een draft opgenomen.

`gsp-draft-qa` weigert elke draft waarbij een van bovenstaande velden ontbreekt of niet aan de voorwaarde voldoet (zie checklist §7).

---

## 3. Eerste bericht — vaste tekstblokken en regels

### 3.1 Toon
- Plain, direct, geen overdrijving, geen "spannende kans" of vergelijkbare wervingstaal.
- Altijd als bedrijf ("wij"), nooit een naam van een individuele medewerker of oprichter als afzender.
- Kort: waarom dit bericht, wat wij aanbieden, wat de ontvanger kan doen (reageren of afmelden).

### 3.2 Art. 14-kennisgevingsblok — verplicht in elk eerste bericht, behalve twee grondslagen

Wanneer persoonsgegevens niet rechtstreeks van de betrokkene zijn verkregen (sourcing), vereist art. 14 AVG een kennisgeving bij het eerste contact: wie wij zijn, waar de gegevens vandaan komen, het doel, de grondslag, de bewaartermijn en de rechten van betrokkene — inclusief het recht van bezwaar (art. 21 AVG) en het recht om een klacht in te dienen bij de Autoriteit Persoonsgegevens. **Dit blok wordt niet gebruikt voor personen met `lawful_basis` = `portal_registratie` of `opt_in_talentpool`** — die gegevens zijn rechtstreeks van de betrokkene verkregen (art. 13 AVG geldt, en die kennisgeving is al gegeven bij registratie/het talentpool-vinkje zelf); voor hen geldt in elk bericht alleen de STOP-regel van §3.3, niet dit blok. Voor alle overige grondslagen (`gerechtvaardigd_belang`, `toestemming_referral`) is dit blok verplicht in elk eerste bericht. Vaste tekst, niet aan te passen per bericht behalve de vierkante haken. `[bron-omschrijving]` wisselt per kanaal — zie de varianten onder dit blok.

**NL:**
> *Dit bericht komt van GSP Recruitment (Brainport/Eindhoven), [functioneel e-mailadres, geen persoonsnaam]. Wij vonden uw [bron-omschrijving] op [datum] in het kader van werving voor technische functies (embedded software, C++, mechatronica, OT-cybersecurity). Grondslag: gerechtvaardigd belang bij werving. Wij bewaren deze gegevens 3 maanden na [datum] als u niet reageert; bij interesse gelden de bewaartermijnen op gsprecruitment.nl/privacy. U kunt op elk moment inzage, correctie of verwijdering vragen. U heeft het recht om bezwaar te maken tegen deze verwerking (art. 21 AVG). U kunt zich afmelden door te antwoorden met "STOP" — wij verwerken dat binnen 24 uur: wij verwijderen uw gegevens uit onze actieve bestanden en uw e-mailadres blijft alleen op een blokkeerlijst zodat wij u niet opnieuw benaderen. Een klacht over deze verwerking kunt u indienen bij de Autoriteit Persoonsgegevens (autoriteitpersoonsgegevens.nl).*

**EN:**
> *This message is from GSP Recruitment (Brainport/Eindhoven, NL), [functional mailbox, no personal name]. We found your [source description] on [date] as part of recruitment for technical roles (embedded software, C++, mechatronics, OT cybersecurity). Legal basis: legitimate interest in recruitment. We retain this data for 3 months after [date] if you do not respond; if you show interest, the retention periods at gsprecruitment.nl/privacy apply. You can request access, correction or deletion at any time. You have the right to object to this processing (Art. 21 GDPR). You can opt out by replying "STOP" — we process that within 24 hours: we remove your data from our active files, and your e-mail address is kept only on a suppression list so we do not contact you again. You can file a complaint about this processing with the Dutch Data Protection Authority (Autoriteit Persoonsgegevens, autoriteitpersoonsgegevens.nl).*

**Varianten voor `[bron-omschrijving]` / `[source description]` — alleen de bracket wisselt, de rest van de zin blijft staan:**
- LinkedIn: *"LinkedIn-profiel via [bron-URL]" / "LinkedIn profile via [source URL]"*
- GitHub: *"GitHub-profiel via [bron-URL]" / "GitHub profile via [source URL]"*

**Meetup en referral: de hele tweede zin wordt vervangen, niet alleen de bracket.** Voor deze twee kanalen vervalt de zin "Wij vonden uw [bron-omschrijving] op [datum] in het kader van..." volledig en wordt zij vervangen door onderstaande vaste zin; de rest van het blok (grondslag, bewaartermijn, rechten, STOP, klachtrecht) blijft ongewijzigd staan.
- Meetup/community (NL): *"Wij hebben uw gegevens gekregen tijdens ons gesprek bij [event] op [datum]."*
- Meetup/community (EN): *"We received your details during our conversation at [event] on [date]."*
- Referral (NL): *"Wij hebben uw gegevens op [datum] gekregen via een aanbeveling van [naam/relatie], met uw toestemming."*
- Referral (EN): *"We received your details on [date] through a recommendation from [name/relation], with your consent."*

### 3.3 Opt-out-regel
- Elk eerste bericht bevat expliciet de STOP-instructie (zoals hierboven).
- Een STOP-antwoord (of een gelijkwaardig verzoek, in welke taal dan ook) wordt binnen 24 uur verwerkt: de persoon gaat op de suppressielijst en alle actieve outreach-drafts richting die persoon worden ingetrokken.
- De suppressielijst wordt bij elk volgend bericht (ook door andere routines) gecontroleerd vóór verzending.
- Tot WS-E.7: het record wordt geanonimiseerd behalve `email`, krijgt `opt_out=<datum>` in het notitieveld en `consent_withdrawn_at` gezet; `gsp-draft-qa` en `gsp-match-and-draft` controleren op die twee sleutels.

### 3.4 Follow-up
- Maximaal één follow-up, ten vroegste 10 werkdagen na het eerste bericht.
- Geen tweede follow-up, ongeacht kanaal of route. Bij geen reactie op de follow-up geldt de bewaartermijn van §6: 3 maanden na `date_found` zonder reactie.

---

## 4. B2B — prospects en Telecommunicatiewet art. 11.7

- Telecommunicatiewet art. 11.7 verbiedt ongevraagde elektronische communicatie aan natuurlijke personen zonder voorafgaande toestemming, met een uitzondering voor **zakelijke, functionele adressen van rechtspersonen** (bijv. `hr@bedrijf.nl`, niet een privé-Gmail-adres) ([wetten.overheid.nl — Telecommunicatiewet, art. 11.7](https://wetten.overheid.nl/BWBR0009950/); toelichting ACM: [acm.nl](https://www.acm.nl/nl/onderwerpen/telecommunicatie)).
- Praktisch: alleen functionele/zakelijke adressen van rechtspersonen benaderen, of adressen van personen met een vastgelegde `lawful_basis` (opt-in of bestaande relatie).
- **Nooit** privéadressen benaderen, en nooit adressen van eenmanszaken/zzp'ers zonder opt-in — een eenmanszaak is voor deze regel een natuurlijk persoon, geen rechtspersoon.
- Hiring-signal watchlist: uitsluitend publieke carrièrepagina's van een vaste Brainport-watchlist, wekelijks handmatig of via een read-only script gecontroleerd (geen scraping-tool, geen geautomatiseerd bulkverzoek).
- Alle prospectoutreach is draft-only; een mens verstuurt. `client_prospects` heeft verplicht `source_url` en `lawful_basis` (WS-E.7); zonder beide wordt geen draft gemaakt. Een servergate op die twee velden bestaat pas na WS-E.7; tot dan is `gsp-draft-qa` (§7.1) de enige controle.

---

## 5. Kandidaat-toestemming vóór anonieme presentatie aan een klant

Een anonieme presentatie aan een klant (spec-candidate / MPC-outreach) mag alleen na **schriftelijke, expliciete** toestemming van de kandidaat, vastgelegd als `consent_spec_presentation_at`. Dit is een aparte toestemming, los van toestemming voor eerste contact of talentpool-opname.

- **Wat het anonieme profiel wél mag bevatten**: functietitel/discipline, jaren ervaring, technische vaardigheden en tools, opleidingsniveau (zonder instellingsnaam tenzij algemeen, bijv. "TU/e"), beschikbaarheid, gewenste regio/reisbereidheid, indicatie salaris/tarief-range, talen.
- **Wat het niet mag bevatten**: naam, foto, exacte geboortedatum, huidige werkgever (tenzij de kandidaat dat expliciet toestaat), contactgegevens, CV-bestand, BSN/paspoortgegevens, exacte adresgegevens.
- Toestemming wordt per klant/opdracht opnieuw gevraagd wanneer de presentatie een nieuwe context betreft — een eenmalige toestemming dekt niet automatisch elke toekomstige klant.
- `approve_draft` weigert automatisch bij ontbrekende `consent_spec_presentation_at` voor spec-candidate-mails na WS-E.7; tot dan is `gsp-draft-qa` (§7.1) de enige controle.

---

## 6. Bewaartermijnen (WS-E.8, aangevuld met drie rijen als aanname, ter bevestiging door de eigenaar)

Eén bewaartabel, identiek in code (purge-job) en op `privacy.html`:

| Categorie | Bewaartermijn | Bron/opmerking |
|---|---|---|
| Afgewezen sollicitant | 4 weken na `rejected_at` | bron: AP/Recruitee |
| Talentpool met expliciete toestemming | 12 maanden, verlengbaar | WS-C.17 |
| Gesourcete persoon zonder reactie | 3 maanden na `date_found` zonder reactie | aanname, strenger dan de 2 jaar in privacy.html |
| Prospect zonder reactie | 12 maanden | |
| Prospect die wel reageert (relatie) | zolang actief + 12 maanden na laatste contact | aanname |
| Actief portalaccount zonder sollicitatie | zolang account actief; 24 maanden inactiviteit → verwijderen | aanname |
| Referral | zoals gesourcet (3 maanden na `date_found` zonder reactie); herkomst = referrer | zie §1.3 |
| Leads/quiz | 12 maanden | |
| Geplaatste kandidaat (contract- en factuurdata) | 7 jaar | fiscale bewaarplicht |
| Logs | 30 dagen (doel) | vandaag: max 5×20 MB per container, rotatie, geen vaste tijd (Docker json-file `max-size`/`max-file`, WS-E.6) |

**Bij het verstrijken van de termijn**: de apscheduler purge-job (`run_retention_purge()`, dagelijks 04:00 Europe/Amsterdam) verwijdert of anonimiseert de persoon automatisch volgens dezelfde `erase_person`-logica als een handmatig AVG-verzoek (alle tabellen, inclusief CV-bestand op R2/legacy-pad), of verwijdert de rij hard waar dat is aangemerkt (VERWERKINGSREGISTER.md §1.4). Talentpool-personen met `consent_talentpool_until` in de toekomst worden door de purge-job overgeslagen; bij het verstrijken van die datum zonder verlenging volgt automatische verwijdering. **Deze purge-job bestaat sinds WS-E.8, maar staat standaard uit (`RETENTION_PURGE_ENABLED=false`) totdat de eigenaar hem inschakelt; tot dan telt de dagelijkse run alleen per categorie en schrijft niets weg.** Bron van waarheid voor deze tabel: `talent-os/backend/core/retention.py` (VERWERKINGSREGISTER.md §1.4). De 14.687 Apollo-rijen vallen niet onder deze tabel — die worden gewist of krijgen per persoon een echte publieke `source_url`, een losstaand eenmalig traject (WS-E.8, `POST /api/v1/admin/apollo-pool/purge`).

---

## 7. Checklists voor de routines

### 7.1 `gsp-draft-qa` — wat afwijzen

Wijs een draft af (niet goedkeuren) als een van deze waar is:

1. Geen `source_url`, of `source_url` is geen publieke `http(s)`-link naar waar de persoon zelf is gevonden — tenzij het een eigen portalregistratie (§1.4) of opt-in talentpool-contact (§1.5) betreft, die beide geen `source_url` nodig hebben.
2. Geen `lawful_basis` vastgelegd, of bij een kandidaat een waarde buiten de vaste set `gerechtvaardigd_belang` / `opt_in_talentpool` / `toestemming_referral` / `portal_registratie` (§2).
3. Voor `lawful_basis` = `gerechtvaardigd_belang` of `toestemming_referral`: het Art. 14-kennisgevingsblok (§3.2) ontbreekt, is aangepast buiten de toegestane vierkante haken (of, bij meetup/referral, buiten de voorgeschreven volledige-zin-vervanging), of mist een van de verplichte onderdelen: functioneel afzenderadres, bronbeschrijving, bewaartermijn ("3 maanden na `date_found`"), recht van bezwaar (art. 21), de blokkeerlijst-zin bij STOP, en het klachtrecht bij de Autoriteit Persoonsgegevens. Voor `lawful_basis` = `portal_registratie` of `opt_in_talentpool`: het bericht bevat ten onrechte het Art. 14-blok (niet van toepassing, §3.2) — of mist de STOP-regel (§3.3), die voor deze twee grondslagen wél verplicht blijft.
4. De opt-out/STOP-regel (§3.3) ontbreekt in het bericht.
5. Persoon staat op de suppressielijst.
6. `consent_withdrawn_at` is gezet voor deze persoon.
7. Prospect zonder `lawful_basis` = `zakelijk_functioneel_adres`, `opt_in` of `bestaande_relatie`, of een privéadres/eenmanszaak-adres zonder opt-in (Telecommunicatiewet art. 11.7, §4).
8. Spec-candidate/anonieme-presentatie-mail zonder `consent_spec_presentation_at` van de betreffende kandidaat (§5).
9. Dit is al de tweede follow-up, of de follow-up wordt minder dan 10 werkdagen na het eerste bericht verstuurd (§3.4).
10. Tekst bevat verzonnen cijfers, valse urgentie, of een toon die niet NRC/FD-plain is.
11. Verplichte logvelden (§2) zijn niet aanwezig als kolom of, zolang WS-E.7/C.17 nog niet is opgeleverd, niet in het notitieveld in de voorgeschreven sleutel=waarde-vorm.

`gsp-candidate-scout` zoekt niet zelf op LinkedIn of GitHub en logt nergens in. Zij verwerkt uitsluitend personen die een mens volgens §1 heeft gevonden en aangeleverd: zij valideert de velden van §2, noteert kanaal en Art. 14-variant en maakt geen draft zonder volledige velden.

### 7.2 `gsp-candidate-scout` — wat loggen

Bij elke door een mens aangeleverde persoon (§1), vóór opname in de pipeline:

1. `source_url`: de exacte publieke URL waar de persoon is gevonden (LinkedIn-profiel, GitHub-profiel, portfolio) — niet verplicht bij eigen portalregistraties (§1.4) of opt-in talentpool-contact (§1.5).
2. `date_found`: datum van vinden (vandaag) — anker voor de bewaartermijn (3 maanden na `date_found` zonder reactie, §6).
3. Kanaal: LinkedIn / GitHub / referral / portal / talentpool / meetup / overig (§1), en bevestiging dat de mens die de persoon aanleverde dit kanaal handmatig en zonder automatiseringstool heeft gebruikt.
4. `lawful_basis`, uit de vaste set voor kandidaten: `gerechtvaardigd_belang` (LinkedIn/GitHub/meetup) / `opt_in_talentpool` (WS-C.17) / `toestemming_referral` (§1.3) / `portal_registratie` (§1.4).
5. Bij GitHub-sourcing: het specifieke contactkanaal dat de persoon zelf publiceert (nooit een e-mailadres uit een commit of profielveld).
6. Bij referral (`toestemming_referral`) of meetup (`gerechtvaardigd_belang`): de juiste volledige-zin-variant voor het Art. 14-blok noteren (§3.2), inclusief naam/relatie of event/datum. Bij `portal_registratie` of `opt_in_talentpool`: geen Art. 14-blok noteren, alleen bevestigen dat de STOP-regel (§3.3) in het bericht staat.
7. Suppressielijst-check: persoon staat niet op de lijst.
8. Zolang WS-E.7/C.17 nog geen eigen kolommen opleveren: velden 1 t/m 4 vastleggen in het notitieveld in de sleutel=waarde-vorm uit §2.
9. Geen contact en geen draft aanmaken als 1 t/m 4 niet volledig zijn ingevuld (portalregistraties en talentpool-contact uitgezonderd van veld 1, zie §1.4/§1.5).

---

## 8. Verwijzingen

- AP, handreiking scraping door particulieren en private organisaties (2024): https://www.autoriteitpersoonsgegevens.nl/documenten/handreiking-scraping-door-particulieren-en-private-organisaties
- GitHub Acceptable Use Policies: https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies
- LinkedIn User Agreement (Dos and Don'ts, automatisering/scraping): https://www.linkedin.com/legal/user-agreement
- Telecommunicatiewet, art. 11.7: https://wetten.overheid.nl/BWBR0009950/
- ACM, telecommunicatie/telemarketing-regels: https://www.acm.nl/nl/onderwerpen/telecommunicatie
- 040coders: https://www.meetup.com/040coders-nl/
- Bits&Chips Event: https://events.bits-chips.com/
- DSPE: https://www.dspe.nl/
- ICS-security-meetup (Amsterdam Cyber Security for Control Systems): https://www.meetup.com/Amsterdam-Cyber-Security-for-Control-Systems/
- Brainport Eindhoven, job portals: https://brainporteindhoven.com/en/brainport-for-smes/labour-market/function-of-the-job-portals
- Brainport Eindhoven, Employer Talent Hub: https://brainporteindhoven.com/en/brainport-for-smes/labour-market/employer-talent-hub
- TU/e, partner career support program: https://www.tue.nl/en/working-at-tue/scientific-staff/partner-career-support-program
- Holland Expat Center South, voor werkgevers: https://www.hollandexpatcenter.com/for-employers
- GSP privacyverklaring (bewaartermijnen, bronnen, ontvangers): `website/privacy.html`

---

*Zie ook: `MASTERPLAN-2026.md` WS-F.4, WS-F.5, WS-F.10, WS-E.7, WS-E.8, §7 ("AVG en sourcing", "Kandidaatkanalen"), §8.1. Bewaartabel (§6) is identiek aan WS-E.8 en aan de tabel op `website/privacy.html` — bij wijziging van de een, de ander binnen dezelfde PR bijwerken.*
