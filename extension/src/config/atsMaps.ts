// Per-ATS field maps. Adding a new ATS = one entry here (mirrors the backend
// adapter pattern). Each logical field lists candidate CSS selectors (tried in
// order) plus label keywords used as a fallback when selectors miss.
import type { Ats } from "../lib/types";

/** Logical fields we know how to fill from a Chronicle profile. */
export type FieldKey =
  | "firstName"
  | "lastName"
  | "fullName"
  | "email"
  | "phone"
  | "location"
  | "linkedin"
  | "github"
  | "portfolio"
  | "workAuth";

export interface FieldSpec {
  selectors: string[];
  /** Label/placeholder keywords for fuzzy fallback matching. */
  labels?: string[];
}

export type AtsFieldMap = Partial<Record<FieldKey, FieldSpec>>;

export const ATS_MAPS: Record<Ats, AtsFieldMap> = {
  greenhouse: {
    firstName: { selectors: ["#first_name", "input[autocomplete='given-name']"], labels: ["first name"] },
    lastName: { selectors: ["#last_name", "input[autocomplete='family-name']"], labels: ["last name"] },
    email: { selectors: ["#email", "input[type='email']"], labels: ["email"] },
    phone: { selectors: ["#phone", "input[type='tel']"], labels: ["phone"] },
    linkedin: { selectors: ["input[id*='linkedin' i]"], labels: ["linkedin"] },
    github: { selectors: ["input[id*='github' i]"], labels: ["github"] },
    portfolio: { selectors: ["input[id*='website' i]", "input[id*='portfolio' i]"], labels: ["website", "portfolio"] },
    location: { selectors: ["#job_application_location", "input[id*='location' i]", "input[autocomplete='address-level2']"], labels: ["location", "city"] },
  },
  lever: {
    fullName: { selectors: ["input[name='name']"], labels: ["full name", "name"] },
    email: { selectors: ["input[name='email']", "input[type='email']"], labels: ["email"] },
    phone: { selectors: ["input[name='phone']", "input[type='tel']"], labels: ["phone"] },
    linkedin: { selectors: ["input[name='urls[LinkedIn]']", "input[name*='LinkedIn' i]"], labels: ["linkedin"] },
    github: { selectors: ["input[name='urls[GitHub]']", "input[name*='GitHub' i]"], labels: ["github"] },
    portfolio: { selectors: ["input[name='urls[Portfolio]']", "input[name*='Portfolio' i]", "input[name*='Website' i]"], labels: ["portfolio", "website"] },
    location: { selectors: ["input[name='location']"], labels: ["location", "city"] },
  },
  ashby: {
    fullName: { selectors: ["input[name='_systemfield_name']", "input[aria-label*='Name' i]"], labels: ["full name", "name"] },
    email: { selectors: ["input[name='_systemfield_email']", "input[type='email']"], labels: ["email"] },
    phone: { selectors: ["input[name='_systemfield_phone']", "input[type='tel']"], labels: ["phone"] },
    linkedin: { selectors: ["input[aria-label*='LinkedIn' i]"], labels: ["linkedin"] },
    github: { selectors: ["input[aria-label*='GitHub' i]"], labels: ["github"] },
    portfolio: { selectors: ["input[aria-label*='Website' i]", "input[aria-label*='Portfolio' i]"], labels: ["website", "portfolio"] },
    location: { selectors: ["input[aria-label*='Location' i]"], labels: ["location", "city"] },
  },
};
