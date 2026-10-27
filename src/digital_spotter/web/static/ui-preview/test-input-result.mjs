/** Accept only the isolated, non-live V5 calculation for the Devices card. */
export function parseTestInputResult(value) {
  if (value?.version !== 'v5_test_input_v1'
    || value.source !== 'frozen_fitted_medians'
    || value.live !== false
    || value.reference_only !== true
    || value.model_version !== 'digital_spotter_v5_scope_faithful') return null;
  const { raw_probability: raw, calibrated_probability: calibrated, threshold, predicted_class: label } = value;
  if (![raw, calibrated, threshold].every(number => Number.isFinite(number) && number >= 0 && number <= 1)
    || threshold === 0 || threshold === 1
    || (label !== 0 && label !== 1)
    || label !== Number(calibrated >= threshold)) return null;
  return value;
}
