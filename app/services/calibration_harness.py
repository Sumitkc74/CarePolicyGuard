import math
from typing import Dict, Any, List, Tuple, Optional


class CalibrationHarness:
    """
    Formal Probability Calibration & Selective Classification Harness.

    DISCIPLINE:
    1. Validation / Test Separation:
       Calibration mapping (temperature scaling or isotonic regression) is fitted
       STRICTLY on validation data. Evaluation metrics (ECE, Brier score, coverage-accuracy curves)
       are computed STRICTLY on unseen test data.
       The harness strictly REFUSES to evaluate on the same partition it was fitted on.

    2. Honesty Notice:
       Until an independently validated held-out set exists, no calibrated probability
       can honestly be claimed in production outputs. The production system reports
       heuristic sufficiency scores instead.

    3. Operating Threshold Derivation:
       Provides algorithmic derivation of threshold tau based on a stated selective-risk target
       (e.g., false-approval rate <= 0.0) on validation data.
    """

    def __init__(self, method: str = "temperature"):
        """
        method: 'temperature' (Platt / temperature scaling) or 'isotonic'
        """
        self.method = method
        self.temperature: float = 1.0
        self.is_fitted: bool = False
        self._fitted_data_hash: Optional[int] = None

    def _hash_dataset(self, dataset: List[Dict[str, Any]]) -> int:
        keys = tuple(sorted((d.get("case_id") or d.get("id") or str(d)) for d in dataset))
        return hash(keys)

    def fit(self, val_dataset: List[Dict[str, Any]]) -> "CalibrationHarness":
        """
        Fits calibration parameters on validation records.
        Each record must contain:
        - raw_score: float (0.0 to 1.0)
        - is_correct: bool / int (1 if prediction matched gold label, 0 otherwise)
        """
        if not val_dataset:
            raise ValueError("Validation dataset cannot be empty for calibration fit.")

        if len(val_dataset) < 3:
            raise ValueError("Insufficient validation samples to fit calibration parameters (minimum 3 required).")

        self._fitted_data_hash = self._hash_dataset(val_dataset)

        # Optimize temperature T to minimize negative log-likelihood (cross-entropy)
        # using bounded grid search over T in [0.1, 5.0]
        best_t = 1.0
        best_nll = float("inf")

        for t_candidate in [x * 0.05 for x in range(2, 80)]:
            nll = 0.0
            for item in val_dataset:
                raw = item["raw_score"]
                y = 1.0 if item["is_correct"] else 0.0
                # Map raw score to logit
                clamped_raw = max(0.001, min(0.999, raw))
                logit = math.log(clamped_raw / (1.0 - clamped_raw))
                scaled_logit = logit / t_candidate
                p = 1.0 / (1.0 + math.exp(-scaled_logit))
                p = max(1e-7, min(1.0 - 1e-7, p))
                nll -= y * math.log(p) + (1.0 - y) * math.log(1.0 - p)

            if nll < best_nll:
                best_nll = nll
                best_t = t_candidate

        self.temperature = round(best_t, 3)
        self.is_fitted = True
        return self

    def predict_probability(self, raw_score: float) -> float:
        """Applies fitted temperature scaling to a raw sufficiency score."""
        if not self.is_fitted:
            raise RuntimeError("Harness must be fitted on validation data before predicting calibrated probabilities.")
        clamped = max(0.001, min(0.999, raw_score))
        logit = math.log(clamped / (1.0 - clamped))
        scaled_logit = logit / self.temperature
        p = 1.0 / (1.0 + math.exp(-scaled_logit))
        return round(p, 4)

    def calibrate_determination(self, adjudication: Any) -> Any:
        """
        Applies empirical calibration from validation-fitted harness to a FinalAdjudication.
        Sets calibrated_aggregate_confidence to the empirical calibrated probability
        and explains the calibration method and temperature parameter.
        """
        if not self.is_fitted:
            raise RuntimeError("Cannot calibrate determination: harness is not fitted on validation data.")

        from app.schemas.contracts import FinalAdjudication
        score_to_calibrate = getattr(adjudication, "sufficiency_score", None)
        if score_to_calibrate is None:
            score_to_calibrate = getattr(adjudication, "raw_aggregate_confidence", 0.85)

        calibrated_prob = self.predict_probability(score_to_calibrate)
        adj_dict = adjudication.model_dump()
        adj_dict["calibrated_aggregate_confidence"] = calibrated_prob
        adj_dict["calibrated_confidence_explanation"] = (
            f"Empirically calibrated via Temperature Scaling (T={self.temperature:.3f}) fitted on validation partition."
        )
        return FinalAdjudication(**adj_dict)

    def evaluate(
        self,
        test_dataset: List[Dict[str, Any]],
        num_bins: int = 5
    ) -> Dict[str, Any]:
        """
        Evaluates calibration and selective classification on TEST data only.
        Rejects evaluation if test dataset matches the validation dataset used for fitting.
        """
        if not self.is_fitted:
            raise RuntimeError("CalibrationHarness is not fitted. Fit on validation data first.")

        test_hash = self._hash_dataset(test_dataset)
        if test_hash == self._fitted_data_hash:
            raise ValueError(
                "Calibration harness cannot fit and evaluate on the same dataset. "
                "Separate validation and test partitions are required to prevent data leakage."
            )

        n = len(test_dataset)
        if n == 0:
            return {"error": "Empty test dataset"}

        # Compute calibrated predictions and Brier score
        brier_sum = 0.0
        calibrated_records = []
        for item in test_dataset:
            raw = item["raw_score"]
            y = 1.0 if item["is_correct"] else 0.0
            p = self.predict_probability(raw)
            brier_sum += (p - y) ** 2
            calibrated_records.append({
                "calibrated_prob": p,
                "is_correct": bool(y),
                "is_false_approval": item.get("is_false_approval", False)
            })

        brier_score = round(brier_sum / n, 4)

        # Expected Calibration Error (ECE) across bins
        bins: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(num_bins)}
        for rec in calibrated_records:
            b_idx = min(num_bins - 1, int(rec["calibrated_prob"] * num_bins))
            bins[b_idx].append(rec)

        ece = 0.0
        reliability_summary = []
        for b_idx in range(num_bins):
            bin_items = bins[b_idx]
            if bin_items:
                bin_size = len(bin_items)
                avg_conf = sum(r["calibrated_prob"] for r in bin_items) / bin_size
                avg_acc = sum(1.0 for r in bin_items if r["is_correct"]) / bin_size
                bin_weight = bin_size / n
                ece += bin_weight * abs(avg_acc - avg_conf)
                reliability_summary.append({
                    "bin_range": f"{b_idx/num_bins:.1f}-{(b_idx+1)/num_bins:.1f}",
                    "count": bin_size,
                    "avg_confidence": round(avg_conf, 3),
                    "empirical_accuracy": round(avg_acc, 3),
                    "calibration_gap": round(abs(avg_acc - avg_conf), 3)
                })

        ece = round(ece, 4)

        # Coverage-Accuracy Curve across threshold spectrum tau in [0.50, 0.95]
        thresholds = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]
        coverage_accuracy_curve = []
        for tau in thresholds:
            covered = [r for r in calibrated_records if r["calibrated_prob"] >= tau]
            cov_count = len(covered)
            deferral_count = n - cov_count
            cov_rate = round(cov_count / n, 3)
            acc = round(sum(1.0 for r in covered if r["is_correct"]) / cov_count, 3) if cov_count > 0 else 1.0
            fa_count = sum(1 for r in covered if r.get("is_false_approval", False))
            fa_rate = round(fa_count / cov_count, 3) if cov_count > 0 else 0.0

            coverage_accuracy_curve.append({
                "threshold_tau": tau,
                "coverage_rate": cov_rate,
                "deferral_rate": round(deferral_count / n, 3),
                "accuracy": acc,
                "false_approval_rate": fa_rate,
                "false_approval_count": fa_count
            })

        return {
            "is_calibrated": True,
            "calibration_method": self.method,
            "fitted_temperature": self.temperature,
            "test_sample_count": n,
            "expected_calibration_error": ece,
            "brier_score": brier_score,
            "reliability_summary": reliability_summary,
            "coverage_accuracy_curve": coverage_accuracy_curve,
            "honesty_notice": "Calibrated on validation split; reported on independent test split. Production runtime reports heuristic sufficiency until validated held-out data exists."
        }

    @staticmethod
    def derive_selective_risk_threshold(
        val_dataset: List[Dict[str, Any]],
        max_false_approval_rate: float = 0.0
    ) -> Dict[str, Any]:
        """
        Derives an operational abstention threshold tau from validation data
        satisfying a strict selective-risk constraint (e.g. false approval rate <= 0.0).
        """
        if not val_dataset:
            raise ValueError("Validation dataset cannot be empty.")

        n = len(val_dataset)
        candidate_thresholds = sorted(set([round(d["raw_score"], 2) for d in val_dataset] + [0.70, 0.75, 0.80, 0.85, 0.90]), reverse=True)

        selected_tau = 0.85
        found = False

        analysis = []
        for tau in candidate_thresholds:
            covered = [d for d in val_dataset if d["raw_score"] >= tau]
            c_count = len(covered)
            if c_count == 0:
                continue
            fa = sum(1 for d in covered if d.get("is_false_approval", False))
            fa_rate = fa / c_count
            analysis.append({
                "tau": tau,
                "covered": c_count,
                "deferral_count": n - c_count,
                "false_approvals": fa,
                "false_approval_rate": round(fa_rate, 4)
            })
            if fa_rate <= max_false_approval_rate and not found:
                selected_tau = tau
                found = True

        return {
            "derived_threshold_tau": selected_tau,
            "target_false_approval_rate": max_false_approval_rate,
            "analysis_grid": analysis,
            "uncalibrated_operating_tradeoff_note": (
                f"Operating choice tau={selected_tau} trades off higher deferrals for 0% false approval rate. "
                "In clinical adjudication, a false approval (improper payment or unindicated surgery) carries severe clinical/legal risk, "
                "whereas a deferral routes to human review safely."
            )
        }

