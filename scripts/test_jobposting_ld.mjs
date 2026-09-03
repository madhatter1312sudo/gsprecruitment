#!/usr/bin/env node
/**
 * WS-A.6 verification: exercises website/vacature.js's buildJobPostingLd()
 * against three fixture jobs and asserts the shape Google's Rich Results
 * Test / JobPosting structured-data guidelines require:
 *   - required fields present: title, description, datePosted,
 *     validThrough, hiringOrganization.name, jobLocation (or
 *     jobLocationType: TELECOMMUTE for a remote posting).
 *   - baseSalary.value.unitText === 'YEAR' only when both salary_min and
 *     salary_max exist; omitted entirely otherwise.
 *   - employmentType mapped from the real vast/detachering/interim field,
 *     never hardcoded to FULL_TIME.
 *   - hiringOrganization.name falls back to "confidential" when
 *     company_display is null (faceless-agency default, matches the
 *     backend's own _public_job_row() projection).
 *
 * Google's actual Rich Results Test needs a public, crawlable URL, so it
 * can't run here -- once this branch is deployed, validate a live
 * /vacature.html?id=<id> URL at https://search.google.com/test/rich-results.
 *
 * Usage: node scripts/test_jobposting_ld.mjs
 * Exits non-zero on any assertion failure.
 */
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const { buildJobPostingLd } = require(path.join(__dirname, '..', 'website', 'vacature.js'));

let failures = 0;
function assert(cond, msg) {
  if (!cond) {
    failures++;
    console.error(`  FAIL: ${msg}`);
  }
}
function ok(msg) {
  console.log(`  ok: ${msg}`);
}

function assertRequiredShape(ld, label) {
  assert(ld['@context'] === 'https://schema.org', `${label}: @context is schema.org`);
  assert(ld['@type'] === 'JobPosting', `${label}: @type is JobPosting`);
  assert(typeof ld.title === 'string' && ld.title.length > 0, `${label}: title present`);
  assert(typeof ld.description === 'string' && ld.description.length > 0, `${label}: description present`);
  assert(typeof ld.datePosted === 'string' && ld.datePosted.length > 0, `${label}: datePosted present`);
  assert(typeof ld.validThrough === 'string' && !isNaN(Date.parse(ld.validThrough)), `${label}: validThrough is a parseable date`);
  assert(ld.hiringOrganization && ld.hiringOrganization['@type'] === 'Organization', `${label}: hiringOrganization.@type is Organization`);
  assert(typeof ld.hiringOrganization.name === 'string' && ld.hiringOrganization.name.length > 0, `${label}: hiringOrganization.name present`);
  const hasPlace = ld.jobLocation && ld.jobLocation['@type'] === 'Place';
  const isRemote = ld.jobLocationType === 'TELECOMMUTE';
  assert(hasPlace || isRemote, `${label}: jobLocation Place present or jobLocationType TELECOMMUTE set`);
  if (hasPlace) {
    assert(ld.jobLocation.address && ld.jobLocation.address['@type'] === 'PostalAddress', `${label}: jobLocation.address is PostalAddress`);
    assert(ld.jobLocation.address.addressCountry === 'NL', `${label}: jobLocation.address.addressCountry is NL`);
  }
}

console.log('Fixture 1: on-site, full salary range, permanent (vast)');
{
  const job = {
    id: 1,
    title: 'Embedded Software Engineer (C++)',
    description: 'We are looking for an embedded C++ engineer for a Brainport high-tech client.',
    created_at: '2026-08-01T09:00:00Z',
    city: 'Eindhoven',
    location_type: 'on-site',
    company_display: 'Confidential Brainport client',
    employment_type: 'vast',
    sponsorship_possible: true,
    salary_min: 55000,
    salary_max: 75000,
    salary_currency: 'EUR',
  };
  const ld = buildJobPostingLd(job);
  assertRequiredShape(ld, 'fixture1');
  assert(ld.employmentType === 'FULL_TIME', 'fixture1: vast maps to FULL_TIME');
  assert(ld.hiringOrganization.name === 'Confidential Brainport client', 'fixture1: hiringOrganization.name from company_display');
  assert(ld.jobLocation.address.addressLocality === 'Eindhoven', 'fixture1: jobLocation.address.addressLocality from city');
  assert(!ld.jobLocationType, 'fixture1: not TELECOMMUTE (on-site)');
  assert(ld.baseSalary && ld.baseSalary['@type'] === 'MonetaryAmount', 'fixture1: baseSalary present');
  assert(ld.baseSalary.currency === 'EUR', 'fixture1: baseSalary.currency EUR');
  assert(ld.baseSalary.value.unitText === 'YEAR', 'fixture1: baseSalary.value.unitText YEAR');
  assert(ld.baseSalary.value.minValue === 55000 && ld.baseSalary.value.maxValue === 75000, 'fixture1: baseSalary.value min/max');
  const expectedValidThrough = new Date('2026-08-01T09:00:00Z');
  expectedValidThrough.setUTCDate(expectedValidThrough.getUTCDate() + 60);
  assert(ld.validThrough === expectedValidThrough.toISOString(), 'fixture1: validThrough = created_at + 60 days');
  ok('fixture1 passed');
}

console.log('\nFixture 2: remote, no company_display, no salary, detachering');
{
  const job = {
    id: 2,
    title: 'OT Cybersecurity Consultant',
    description: 'Detachering-opdracht bij een industriele klant, remote werken mogelijk.',
    created_at: '2026-09-01T12:00:00Z',
    city: null,
    location_type: 'remote',
    company_display: null,
    employment_type: 'detachering',
    salary_min: null,
    salary_max: null,
  };
  const ld = buildJobPostingLd(job);
  assertRequiredShape(ld, 'fixture2');
  assert(ld.employmentType === 'CONTRACTOR', 'fixture2: detachering maps to CONTRACTOR');
  assert(ld.hiringOrganization.name === 'confidential', 'fixture2: hiringOrganization.name falls back to confidential');
  assert(ld.jobLocationType === 'TELECOMMUTE', 'fixture2: jobLocationType TELECOMMUTE for remote');
  assert(ld.baseSalary === undefined, 'fixture2: baseSalary omitted when salary_min/max are null');
  ok('fixture2 passed');
}

console.log('\nFixture 3: interim, only salary_min set (no baseSalary), explicit expiry');
{
  const job = {
    id: 3,
    title: 'Interim Mechatronica Engineer',
    description: 'Interim opdracht, machinebouw.',
    created_at: '2026-07-15T08:00:00Z',
    city: 'Helmond',
    location_type: 'hybrid',
    company_display: 'confidential',
    employment_type: 'interim',
    salary_min: 90,
    salary_max: null,
    valid_through: '2026-10-01T00:00:00Z',
  };
  const ld = buildJobPostingLd(job);
  assertRequiredShape(ld, 'fixture3');
  assert(ld.employmentType === 'TEMPORARY', 'fixture3: interim maps to TEMPORARY');
  assert(ld.baseSalary === undefined, 'fixture3: baseSalary omitted when only salary_min is set');
  assert(ld.validThrough === '2026-10-01T00:00:00Z', 'fixture3: validThrough honors the job\'s own expiry over created_at + 60');
  assert(!ld.jobLocationType, 'fixture3: not TELECOMMUTE (hybrid)');
  ok('fixture3 passed');
}

console.log(`\n${failures === 0 ? 'PASS' : 'FAIL'}: ${failures} assertion failure(s).`);
process.exit(failures === 0 ? 0 : 1);
