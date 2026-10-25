import { FinalAdjudication, PeerToPeerAppealLetter, MedicarePolicy } from "./types";

// Default localhost for Android emulator (10.0.2.2) or iOS simulator/physical device (localhost or LAN IP)
const API_BASE_URL = "http://10.0.2.2:8000/api/v1";

export class ApiService {
  private static baseUrl = API_BASE_URL;

  public static setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  public static async fetchPolicies(): Promise<MedicarePolicy[]> {
    try {
      const res = await fetch(`${this.baseUrl}/policies`);
      if (!res.ok) throw new Error("Failed to fetch policies");
      return await res.json();
    } catch (err) {
      console.warn("API offline, returning fallback policies");
      return [
        { policy_id: "NCD-20.4", title: "Implantable Automatic Defibrillators (ICDs)", category: "Cardiology", description: "Severe systolic dysfunction LVEF <= 35%, NYHA II/III, GDMT >= 90 days." },
        { policy_id: "LCD-L33829", title: "Positive Airway Pressure (CPAP) for Sleep Apnea", category: "Pulmonology", description: "Polysomnography AHI >= 15 or AHI 5-14 with comorbidity." },
        { policy_id: "NCD-20.33", title: "Transcatheter Edge-to-Edge Repair (TEER / MitraClip)", category: "Cardiology", description: "Grade 3+/4+ Mitral Regurgitation with Heart Team consensus." }
      ];
    }
  }

  public static async adjudicateNote(
    patientId: string,
    policyId: string,
    narrative: string,
    cptCode?: string
  ): Promise<FinalAdjudication> {
    const res = await fetch(`${this.baseUrl}/adjudicate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        patient_id: patientId || "PT-MOBILE-APP",
        policy_id: policyId,
        ehr_narrative: narrative,
        cpt_codes: cptCode ? [cptCode] : undefined
      })
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Adjudication failed: ${res.status} - ${errText}`);
    }

    return await res.json();
  }

  public static async generateAppealLetter(caseId: string): Promise<PeerToPeerAppealLetter> {
    const res = await fetch(`${this.baseUrl}/packet/${caseId}/appeal-letter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });

    if (!res.ok) {
      throw new Error("Failed to generate appeal brief");
    }

    return await res.json();
  }
}

