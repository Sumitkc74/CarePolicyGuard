import React, { useState } from "react";
import {
  StyleSheet,
  Text,
  View,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  useWindowDimensions,
  Platform,
  SafeAreaView,
  StatusBar
} from "react-native";
import { FinalAdjudication, PeerToPeerAppealLetter } from "./types";
import { ApiService } from "./api";

const PRESET_CARDIOLOGY = `68-year-old male with ischemic cardiomyopathy. Prior MI in 2021 (>3 years ago). Echo on 01/10/2024 shows severe systolic dysfunction with LVEF 28%. NYHA Class II symptoms with mild dyspnea on exertion. On guideline-directed medical therapy for >6 months with Carvedilol 25mg BID, Lisinopril 20mg daily, and Spironolactone 25mg daily. No cardiogenic shock, no terminal illness.`;
const PRESET_RECENT_MI = `55-year-old female post acute STEMI 12 days ago. Underwent emergency stenting. Echo demonstrates LVEF 30%. NYHA Class II. Currently in hospital recovering from acute event.`;
const PRESET_SLEEP = `52-year-old male with chronic severe snoring and witnessed apneas. Prior in-person face-to-face evaluation by Dr. Stevens documented severe daytime somnolence (Epworth 16/24). Diagnostic polysomnography performed showing severe OSA with AHI 36.4 events/hr. Recommending auto-CPAP trial.`;

export default function App() {
  const { width, height } = useWindowDimensions();
  const isTabletOrDesktop = width >= 768;
  const isSmallPhone = width < 375;

  const [activeTab, setActiveTab] = useState<"adjudicate" | "result" | "appeal">("adjudicate");
  const [patientId, setPatientId] = useState("PT-ROUNDS-001");
  const [selectedPolicy, setSelectedPolicy] = useState("NCD-20.4");
  const [clinicalNote, setClinicalNote] = useState(PRESET_CARDIOLOGY);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<FinalAdjudication | null>(null);
  const [appeal, setAppeal] = useState<PeerToPeerAppealLetter | null>(null);

  const handleRunVerification = async () => {
    if (!clinicalNote.trim()) {
      Alert.alert("Missing Note", "Please enter or paste a patient note first.");
      return;
    }

    setLoading(true);
    try {
      const data = await ApiService.adjudicateNote(patientId, selectedPolicy, clinicalNote);
      setResult(data);
      setActiveTab("result");
    } catch (err: any) {
      Alert.alert("Verification Error", err.message || "Failed to reach backend API.");
    } finally {
      setLoading(false);
    }
  };

  const handleLoadAppeal = async () => {
    if (!result) return;
    setLoading(true);
    try {
      const appealData = await ApiService.generateAppealLetter(result.case_id);
      setAppeal(appealData);
      setActiveTab("appeal");
    } catch (err: any) {
      Alert.alert("Appeal Error", err.message || "Could not generate appeal brief.");
    } finally {
      setLoading(false);
    }
  };

  // Max width container for iPad / tablets / web browser view
  const contentContainerStyle = [
    styles.content,
    isTabletOrDesktop && { maxWidth: 840, width: "100%", alignSelf: "center" as const }
  ];

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" backgroundColor="#0f172a" />
      <View style={styles.container}>
        {/* Top Header */}
        <View style={[styles.header, isTabletOrDesktop && styles.headerTablet]}>
          <View style={isTabletOrDesktop ? styles.tabletHeaderInner : undefined}>
            <Text style={styles.headerTitle}>CarePolicy<Text style={styles.headerAccent}>Guard</Text></Text>
            <Text style={styles.headerSubtitle}>Mobile Clinical Prior-Auth CDS &bull; Medicare Rule Engine</Text>
          </View>
        </View>

        {/* Navigation Tabs */}
        <View style={styles.tabBarWrapper}>
          <View style={[styles.tabBar, isTabletOrDesktop && { maxWidth: 840, width: "100%", alignSelf: "center" }]}>
            <TouchableOpacity
              style={[styles.tabButton, activeTab === "adjudicate" && styles.tabButtonActive]}
              onPress={() => setActiveTab("adjudicate")}
            >
              <Text style={[styles.tabText, activeTab === "adjudicate" && styles.tabTextActive]}>1. Note Entry</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.tabButton, activeTab === "result" && styles.tabButtonActive]}
              onPress={() => result && setActiveTab("result")}
              disabled={!result}
            >
              <Text style={[styles.tabText, activeTab === "result" && styles.tabTextActive, !result && styles.tabTextDisabled]}>
                2. Determination
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.tabButton, activeTab === "appeal" && styles.tabButtonActive]}
              onPress={() => appeal && setActiveTab("appeal")}
              disabled={!appeal}
            >
              <Text style={[styles.tabText, activeTab === "appeal" && styles.tabTextActive, !appeal && styles.tabTextDisabled]}>
                3. Peer Appeal
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        <ScrollView style={styles.scrollWrapper} contentContainerStyle={contentContainerStyle}>
          {/* TAB 1: ADJUDICATE */}
          {activeTab === "adjudicate" && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Bedside Consultation Note</Text>
              <Text style={styles.cardDesc}>Evaluate patient against statutory Medicare NCD/LCD guidelines in real time.</Text>

              <Text style={styles.inputLabel}>Patient ID / Bed:</Text>
              <TextInput
                style={styles.input}
                value={patientId}
                onChangeText={setPatientId}
                placeholder="e.g. PT-ROUNDS-001"
                placeholderTextColor="#64748b"
              />

              <Text style={styles.inputLabel}>Target Medicare Policy:</Text>
              <View style={[styles.chipRow, isSmallPhone && { flexDirection: "column", gap: 6 }]}>
                <TouchableOpacity
                  style={[styles.chip, selectedPolicy === "NCD-20.4" && styles.chipActive]}
                  onPress={() => setSelectedPolicy("NCD-20.4")}
                >
                  <Text style={[styles.chipText, selectedPolicy === "NCD-20.4" && styles.chipTextActive]}>Cardiology ICD (NCD-20.4)</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.chip, selectedPolicy === "LCD-L33829" && styles.chipActive]}
                  onPress={() => setSelectedPolicy("LCD-L33829")}
                >
                  <Text style={[styles.chipText, selectedPolicy === "LCD-L33829" && styles.chipTextActive]}>Sleep CPAP (LCD-L33829)</Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.inputLabel}>Quick Roster Presets:</Text>
              <View style={styles.presetRow}>
                <TouchableOpacity style={styles.presetBtn} onPress={() => setClinicalNote(PRESET_CARDIOLOGY)}>
                  <Text style={styles.presetText}>Passing ICD</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.presetBtn} onPress={() => setClinicalNote(PRESET_RECENT_MI)}>
                  <Text style={styles.presetText}>Recent MI (&lt;40d)</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.presetBtn} onPress={() => { setSelectedPolicy("LCD-L33829"); setClinicalNote(PRESET_SLEEP); }}>
                  <Text style={styles.presetText}>Severe OSA</Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.inputLabel}>Clinical Narrative Note:</Text>
              <TextInput
                style={[styles.textArea, isTabletOrDesktop && { minHeight: 180 }]}
                value={clinicalNote}
                onChangeText={setClinicalNote}
                multiline
                numberOfLines={8}
                placeholder="Enter or dictate patient progress note..."
                placeholderTextColor="#64748b"
              />

              <TouchableOpacity style={styles.submitBtn} onPress={handleRunVerification} disabled={loading}>
                {loading ? (
                  <ActivityIndicator color="#090d16" />
                ) : (
                  <Text style={styles.submitBtnText}>Verify Prior Authorization</Text>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* TAB 2: RESULT */}
          {activeTab === "result" && result && (
            <View>
              {/* Status Banner */}
              <View style={[
                styles.decisionBanner,
                result.adjudication_decision === "APPROVED" ? styles.bannerApproved :
                result.adjudication_decision === "DENIED" ? styles.bannerDenied : styles.bannerDeferred
              ]}>
                <Text style={styles.decisionTitle}>{result.adjudication_decision.replace(/_/g, " ")}</Text>
                <Text style={styles.decisionSubtitle}>
                  Confidence: {Math.round(result.calibrated_aggregate_confidence * 100)}% | Safety Gate: {result.abstention_status ? "Abstained (tau < 0.85)" : "Passed (tau >= 0.85)"}
                </Text>
                <Text style={styles.caseIdText}>Case: {result.case_id} &bull; {result.patient_id_masked}</Text>
              </View>

              {/* Criteria List */}
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Criteria Breakdown ({result.policy_id})</Text>
                {result.criterion_assessments.map((crit, idx) => (
                  <View key={idx} style={styles.critRow}>
                    <View style={styles.critHeader}>
                      <Text style={styles.critCode}>[{crit.criterion_code}]</Text>
                      <Text style={[
                        styles.critStatus,
                        crit.status === "MET" ? styles.statusMet :
                        crit.status === "NOT_MET" ? styles.statusNotMet : styles.statusInsufficient
                      ]}>
                        {crit.status}
                      </Text>
                    </View>
                    <Text style={styles.critName}>{crit.name || crit.description}</Text>
                    <Text style={styles.critRationale}>{crit.clinical_rationale}</Text>
                    {crit.verified_spans.length > 0 && (
                      <View style={styles.spanBox}>
                        <Text style={styles.spanTitle}>Grounded Note Quote:</Text>
                        <Text style={styles.spanText}>"{crit.verified_spans[0].source_text}"</Text>
                      </View>
                    )}
                  </View>
                ))}

                <TouchableOpacity style={styles.appealActionBtn} onPress={handleLoadAppeal} disabled={loading}>
                  <Text style={styles.appealActionBtnText}>View Peer-to-Peer Appeal Brief &rarr;</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* TAB 3: APPEAL BRIEF */}
          {activeTab === "appeal" && appeal && (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Peer-to-Peer Verbal Defense</Text>
              <Text style={styles.cardDesc}>Talking points for phone call with Medicare Medical Director:</Text>

              {appeal.peer_to_peer_talking_points.map((pt, idx) => (
                <View key={idx} style={styles.bulletRow}>
                  <Text style={styles.bullet}>&bull;</Text>
                  <Text style={styles.bulletText}>{pt}</Text>
                </View>
              ))}

              <Text style={[styles.cardTitle, { marginTop: 18 }]}>Formal Letter Brief</Text>
              <View style={styles.letterPaper}>
                <Text style={styles.letterText}>{appeal.full_letter_text}</Text>
              </View>
            </View>
          )}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: "#0f172a" },
  container: { flex: 1, backgroundColor: "#090d16" },
  header: {
    paddingTop: Platform.OS === "android" ? 15 : 10,
    paddingBottom: 15,
    paddingHorizontal: 20,
    backgroundColor: "#0f172a",
    borderBottomWidth: 1,
    borderColor: "#1e293b"
  },
  headerTablet: { alignItems: "center" },
  tabletHeaderInner: { maxWidth: 840, width: "100%" },
  headerTitle: { fontSize: 20, fontWeight: "700", color: "#f8fafc" },
  headerAccent: { color: "#38bdf8" },
  headerSubtitle: { fontSize: 12, color: "#94a3b8", marginTop: 2 },
  tabBarWrapper: { backgroundColor: "#0f172a", borderBottomWidth: 1, borderColor: "#1e293b" },
  tabBar: { flexDirection: "row" },
  tabButton: { flex: 1, paddingVertical: 12, alignItems: "center" },
  tabButtonActive: { borderBottomWidth: 2, borderColor: "#38bdf8" },
  tabText: { fontSize: 13, color: "#64748b", fontWeight: "600" },
  tabTextActive: { color: "#38bdf8" },
  tabTextDisabled: { color: "#334155" },
  scrollWrapper: { flex: 1 },
  content: { padding: 16, paddingBottom: 40 },
  card: { backgroundColor: "#0f172a", borderRadius: 12, padding: 16, borderWidth: 1, borderColor: "#1e293b", marginBottom: 20 },
  cardTitle: { fontSize: 16, fontWeight: "700", color: "#f1f5f9", marginBottom: 4 },
  cardDesc: { fontSize: 12, color: "#94a3b8", marginBottom: 14 },
  inputLabel: { fontSize: 12, fontWeight: "600", color: "#cbd5e1", marginTop: 10, marginBottom: 6 },
  input: { backgroundColor: "#090d16", borderWidth: 1, borderColor: "#334155", borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, color: "#f8fafc", fontSize: 14 },
  chipRow: { flexDirection: "row", gap: 8, marginBottom: 6, flexWrap: "wrap" },
  chip: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 20, backgroundColor: "#1e293b", alignSelf: "flex-start" },
  chipActive: { backgroundColor: "rgba(56, 189, 248, 0.2)", borderWidth: 1, borderColor: "#38bdf8" },
  chipText: { fontSize: 12, color: "#94a3b8" },
  chipTextActive: { color: "#38bdf8", fontWeight: "600" },
  presetRow: { flexDirection: "row", gap: 6, marginBottom: 8, flexWrap: "wrap" },
  presetBtn: { backgroundColor: "#1e293b", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6 },
  presetText: { fontSize: 11, color: "#94a3b8" },
  textArea: { backgroundColor: "#090d16", borderWidth: 1, borderColor: "#334155", borderRadius: 8, padding: 12, color: "#f8fafc", fontSize: 13, minHeight: 120, textAlignVertical: "top" },
  submitBtn: { backgroundColor: "#38bdf8", borderRadius: 8, paddingVertical: 14, alignItems: "center", marginTop: 18 },
  submitBtnText: { color: "#090d16", fontWeight: "700", fontSize: 14 },
  decisionBanner: { padding: 18, borderRadius: 12, marginBottom: 16, alignItems: "center" },
  bannerApproved: { backgroundColor: "rgba(16, 185, 129, 0.15)", borderWidth: 1, borderColor: "#10b981" },
  bannerDenied: { backgroundColor: "rgba(239, 68, 68, 0.15)", borderWidth: 1, borderColor: "#ef4444" },
  bannerDeferred: { backgroundColor: "rgba(245, 158, 11, 0.15)", borderWidth: 1, borderColor: "#f59e0b" },
  decisionTitle: { fontSize: 20, fontWeight: "800", color: "#f8fafc", letterSpacing: 0.5 },
  decisionSubtitle: { fontSize: 12, color: "#cbd5e1", marginTop: 4, textAlign: "center" },
  caseIdText: { fontSize: 11, color: "#64748b", marginTop: 4 },
  critRow: { borderBottomWidth: 1, borderColor: "#1e293b", paddingVertical: 12 },
  critHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  critCode: { fontSize: 11, fontWeight: "700", color: "#38bdf8", fontFamily: Platform.OS === "ios" ? "Courier" : "monospace" },
  critStatus: { fontSize: 10, fontWeight: "700", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  statusMet: { backgroundColor: "rgba(16, 185, 129, 0.2)", color: "#10b981" },
  statusNotMet: { backgroundColor: "rgba(239, 68, 68, 0.2)", color: "#ef4444" },
  statusInsufficient: { backgroundColor: "rgba(245, 158, 11, 0.2)", color: "#f59e0b" },
  critName: { fontSize: 13, fontWeight: "600", color: "#e2e8f0", marginBottom: 2 },
  critRationale: { fontSize: 12, color: "#94a3b8" },
  spanBox: { backgroundColor: "#090d16", padding: 8, borderRadius: 6, marginTop: 6, borderLeftWidth: 2, borderColor: "#10b981" },
  spanTitle: { fontSize: 10, color: "#10b981", fontWeight: "700" },
  spanText: { fontSize: 11, color: "#cbd5e1", fontStyle: "italic", marginTop: 2 },
  appealActionBtn: { marginTop: 16, backgroundColor: "#1e293b", paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  appealActionBtnText: { color: "#38bdf8", fontWeight: "600", fontSize: 13 },
  bulletRow: { flexDirection: "row", marginBottom: 8 },
  bullet: { color: "#f59e0b", fontSize: 16, marginRight: 8 },
  bulletText: { color: "#cbd5e1", fontSize: 12, flex: 1, lineHeight: 18 },
  letterPaper: { backgroundColor: "#090d16", padding: 12, borderRadius: 8, borderWidth: 1, borderColor: "#1e293b", marginTop: 10 },
  letterText: { color: "#94a3b8", fontSize: 11, fontFamily: Platform.OS === "ios" ? "Courier" : "monospace", lineHeight: 16 }
});
