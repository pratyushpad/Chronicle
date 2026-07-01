// Fill form fields from a Chronicle profile. FILL-ONLY: this module never calls
// form.submit(), never clicks a submit control, and never dispatches a submit event.
import { ATS_MAPS, type AtsFieldMap, type FieldKey } from "../config/atsMaps";
import type { Ats, FillResult, ProfileData } from "../lib/types";

type FillInput = HTMLInputElement | HTMLTextAreaElement;

/** Set a value the way React expects: native setter + input/change events. */
function setValue(el: FillInput, value: string): void {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  setter?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function isFillable(el: Element | null): el is FillInput {
  if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement)) return false;
  if (el.disabled || el.readOnly) return false;
  if (el instanceof HTMLInputElement && ["checkbox", "radio", "file", "submit", "button", "hidden"].includes(el.type)) {
    return false;
  }
  return true;
}

/** Resolve an element for a field: try selectors first, then label/placeholder text. */
function resolve(map: AtsFieldMap, key: FieldKey): FillInput | null {
  const spec = map[key];
  if (!spec) return null;
  for (const sel of spec.selectors) {
    const el = document.querySelector(sel);
    if (isFillable(el)) return el;
  }
  if (spec.labels?.length) {
    for (const el of Array.from(document.querySelectorAll("input, textarea"))) {
      if (!isFillable(el)) continue;
      const hay = [
        el.getAttribute("placeholder"),
        el.getAttribute("aria-label"),
        el.getAttribute("name"),
        labelTextFor(el),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      if (spec.labels.some((l) => hay.includes(l))) return el;
    }
  }
  return null;
}

function labelTextFor(el: Element): string {
  const id = el.getAttribute("id");
  if (id) {
    const lbl = document.querySelector(`label[for='${CSS.escape(id)}']`);
    if (lbl?.textContent) return lbl.textContent;
  }
  return el.closest("label")?.textContent ?? "";
}

/** Build the concrete value for each logical field from the profile. */
function fieldValues(profile: ProfileData): Partial<Record<FieldKey, string>> {
  const full = (profile.full_name ?? "").trim();
  const [first, ...rest] = full.split(/\s+/);
  const links = profile.links ?? {};
  const out: Partial<Record<FieldKey, string>> = {};
  const put = (k: FieldKey, v: string | null | undefined) => {
    if (v && v.trim()) out[k] = v.trim();
  };
  put("fullName", full);
  put("firstName", first);
  put("lastName", rest.join(" "));
  put("email", profile.email);
  put("phone", profile.phone);
  put("location", profile.location);
  put("workAuth", profile.work_authorization);
  put("linkedin", links.linkedin);
  put("github", links.github);
  put("portfolio", links.portfolio);
  return out;
}

export function fillPage(ats: Ats, profile: ProfileData): FillResult {
  const map = ATS_MAPS[ats];
  const values = fieldValues(profile);
  const filled: string[] = [];
  for (const key of Object.keys(values) as FieldKey[]) {
    const el = resolve(map, key);
    if (el) {
      setValue(el, values[key]!);
      filled.push(key);
    }
  }
  return { ok: true, filled: filled.length, fields: filled };
}
