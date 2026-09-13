/* ============================================================
   GSP Recruitment — admin/js/labels.js
   Alle enum -> labelvertalingen van het adminpaneel op één plek,
   Nederlandstalig. Hiervoor stonden dit zes losse mapjes verspreid over
   admin.js (statusLabel, erkendReferentLabel, roleLabel,
   activityTypeLabel, leadInterestLabel, dienstlijnLabel).

   De sleutels zijn de echte waarden die de backend schrijft of accepteert,
   niet verzonnen:
     - kandidaatstatus:  candidates.status, VARCHAR met default 'sourced'
                         (migrations/000_baseline.py). De pipeline-waarden
                         hieronder zijn wat GET /v1/admin/candidates
                         teruggeeft.
     - erkendReferent:   ClientUpdate.erkend_referent, pattern
                         ^(ja|nee|onbekend)$ (models/schemas.py)
     - contactRol:       ClientContact*.role, pattern
                         ^(hiring_manager|finance|tekenbevoegd|overig)$
     - activiteit:       ACTIVITY_TYPES = ("note", "call", "email",
                         "meeting", "task", "status_change")
     - leadCategorie:    LEAD_INTEREST_TYPES = ("werving_selectie",
                         "detachering_internationaal", "kandidaat",
                         "overig")
     - dienstlijn:       jobs.employment_type, Literal["vast",
                         "detachering", "interim"]. De twee
                         leadcategorienamen staan er ook in omdat oudere
                         vacaturerijen die waarde dragen.

   Ter referentie, nog niet gekoppeld: core/sources.py kent vijf literals
   voor candidates.source (portal_registration, talentpool_optin, apollo,
   apollo_bulk, agent) plus vrije waarden van een API-caller. Het
   kandidaatpaneel toont source nu nog ruw; dat vertalen hoort bij de
   sectiepass op basis van componentspec §7, niet bij deze refactor.

   Onbekende waarden vallen terug op de waarde zelf (nooit stil verborgen)
   of op een expliciete fallback.
   ============================================================ */
(function (root) {
  'use strict';

  const MAPS = {
    kandidaatstatus: {
      sourced: 'Gesourced', new: 'Nieuw', contacted: 'Benaderd',
      screening: 'Screening', active: 'Actief', placed: 'Geplaatst',
      inactive: 'Inactief',
    },
    erkendReferent: { ja: 'Ja', nee: 'Nee', onbekend: 'Onbekend' },
    contactRol: {
      hiring_manager: 'Hiring manager', finance: 'Financiën',
      tekenbevoegd: 'Tekenbevoegd', overig: 'Overig',
    },
    activiteit: {
      note: 'Notitie', call: 'Telefoongesprek', email: 'E-mail',
      meeting: 'Afspraak', task: 'Taak', status_change: 'Statuswijziging',
    },
    leadCategorie: {
      // Let op: de leadinbox schrijft dit als "Werving & selectie" (zoals
      // de filteroptie in index.html), de dienstlijnmap hieronder als
      // "Werving en selectie" (zoals de vacaturekolom). Bewust ongemoeid
      // gelaten: de kopij van beide is een sectiepass, geen refactor.
      werving_selectie: 'Werving & selectie',
      detachering_internationaal: 'Detachering (internationaal)',
      kandidaat: 'Kandidaat', overig: 'Overig',
    },
    dienstlijn: {
      vast: 'Vast (werving en selectie)',
      detachering: 'Detachering',
      interim: 'Interim',
      werving_selectie: 'Werving en selectie',
      detachering_internationaal: 'Detachering (internationaal)',
    },
    // De drie retentiemaps komen letterlijk uit SITE-DESIGN-SPEC.md §7.2e.
    // De categorielabels zijn de `categorie`-tekst uit RETENTION_TABLE
    // (core/retention.py), verbatim, want diezelfde tekst staat in het
    // verwerkingsregister en op privacy.html en mag niet uiteenlopen.
    // apollo_pool_purge is de uitzondering: die categorie heeft geen
    // RETENTION_TABLE-rij (services/scheduler.py zet hem rechtstreeks in de
    // wachtrij), dus dit label is UI-eigen.
    retentiestatus: {
      pending: 'Te beoordelen',
      rejected: 'Afgewezen (bewaard)',
      purging: 'Wordt verwerkt',
      purged: 'Verwerkt',
      no_longer_eligible: 'Niet meer van toepassing',
    },
    retentiecategorie: {
      rejected_applicant: 'Afgewezen sollicitant',
      talentpool_consent: 'Talentpool met expliciete toestemming',
      sourced_no_response: 'Gesourcete persoon zonder reactie',
      prospect_no_response: 'Prospect zonder reactie',
      prospect_responding: 'Prospect die wel reageert (relatie)',
      portal_account_inactive: 'Actief portalaccount zonder sollicitatie',
      referral: 'Referral',
      leads_quiz: 'Leads/quiz',
      // Deze twee komen nooit in de beoordelingslijst (action retain
      // respectievelijk infra_only), maar wel in de bewaartabel en in de
      // droogloop, dus zonder deze twee regels staat daar de ruwe sleutel.
      placed_candidate: 'Geplaatste kandidaat (contract- en factuurdata)',
      logs: 'Logs',
      // De enige UI-eigen naam: apollo_pool_purge heeft geen
      // RETENTION_TABLE-rij (services/scheduler.py zet hem rechtstreeks in
      // de wachtrij), dus er is geen backendlabel om over te nemen.
      apollo_pool_purge: 'Apollo-bulkpool',
    },
    retentieactie: {
      anonymise: 'Anonimiseren',
      hard_delete: 'Hard verwijderen',
      retain: 'Bewaren',
      infra_only: 'Alleen infrastructuur',
    },
    // retention_review_items.subject_table -> het woord dat in "kandidaat
    // #1482" voor het nummer staat.
    retentieonderwerp: {
      candidates: 'kandidaat',
      client_prospects: 'prospect',
      users: 'portalaccount',
      quiz_submissions: 'quizinzending',
      contact_submissions: 'contactinzending',
    },
    // §7.2e "Grondslag": candidates.lawful_basis (vier vrije-tekstwaarden,
    // core/privacy.py en de referral-route) plus client_prospects.lawful_basis
    // (drie gevalideerde waarden, routers/prospects.py). De kandidaatdrawer
    // (§7.3.2) toont alleen de eerste vier; de prospectselect elders alleen
    // de laatste drie.
    grondslag: {
      portal_registratie: 'Eigen portalaccount (art. 13)',
      opt_in_talentpool: 'Toestemming talentpool',
      toestemming_referral: 'Toestemming via referral',
      gerechtvaardigd_belang: 'Gerechtvaardigd belang',
      zakelijk_functioneel_adres: 'Zakelijk functioneel adres',
      opt_in: 'Opt-in',
      bestaande_relatie: 'Bestaande relatie',
    },
    // §7.2e "Toestemmingsomvang": TALENTPOOL_CONSENT_SCOPES (models/schemas.py).
    toestemmingsomvang: {
      matching_only: 'Alleen matching',
      matching_and_contact: 'Matching en contact',
    },
  };

  // Kleurfamilie per waarde (§7.2e: neutraal, informatief, aandacht,
  // positief, negatief). Alleen voor domeinen waar Admin.badge() de
  // waarde niet kent of anders zou kleuren: `pending` is daar blauw en
  // hier aandacht. Dit is de voorloper van de {label, tone}-vorm die
  // js/status-map.js in de §7.2e-pass krijgt.
  const TONES = {
    retentiestatus: {
      pending: 'aandacht', rejected: 'neutraal', purging: 'informatief',
      purged: 'positief', no_longer_eligible: 'neutraal',
    },
  };

  const TONE_CLASS = {
    neutraal: 'bg-secondary-lt', informatief: 'bg-blue-lt',
    aandacht: 'bg-yellow-lt', positief: 'bg-green-lt', negatief: 'bg-red-lt',
  };

  // label('activiteit', 'call') -> 'Telefoongesprek'.
  // Zonder treffer: de fallback als die is meegegeven, anders de waarde
  // zelf (html`` escapet die alsnog), anders een streepje.
  function label(mapName, value, fallback) {
    const map = MAPS[mapName] || {};
    const key = value == null ? '' : String(value).toLowerCase();
    if (map[key]) return map[key];
    if (fallback !== undefined) return fallback;
    return value || '—';
  }

  // badgeClass('retentiestatus', 'pending') -> 'badge bg-yellow-lt'.
  // Een waarde zonder eigen familie wordt neutraal: nooit verbergen,
  // nooit raden.
  function badgeClass(mapName, value) {
    const map = TONES[mapName] || {};
    const key = value == null ? '' : String(value).toLowerCase();
    return 'badge ' + (TONE_CLASS[map[key]] || TONE_CLASS.neutraal);
  }

  root.AdminLabels = { maps: MAPS, tones: TONES, label, badgeClass };

  // De zes bestaande aanroepnamen op Admin blijven bestaan als dunne
  // doorgeefluiken, zodat geen enkele sectie hoefde te veranderen.
  // Let op: admin.js declareert Admin met `const` op scriptniveau, dus het
  // staat wel in de globale scope maar niet als window.Admin -- vandaar de
  // bare identifier met typeof-guard, niet root.Admin.
  if (typeof Admin !== 'undefined') {
    Object.assign(Admin, {
      statusLabel: (v) => label('kandidaatstatus', v, v || 'Actief'),
      erkendReferentLabel: (v) => label('erkendReferent', v, 'Onbekend'),
      roleLabel: (v) => label('contactRol', v, '—'),
      activityTypeLabel: (v) => label('activiteit', v),
      leadInterestLabel: (v) => label('leadCategorie', v, '—'),
      dienstlijnLabel: (v) => MAPS.dienstlijn[v] || v || 'onbekend',
    });
  }
})(typeof window !== 'undefined' ? window : globalThis);
