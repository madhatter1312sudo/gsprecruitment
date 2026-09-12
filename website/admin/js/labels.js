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

  root.AdminLabels = { maps: MAPS, label };

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
