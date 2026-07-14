const API_BASE = window.location.origin;

const form = document.getElementById("visitorForm");
const statusBanner = document.getElementById("statusBanner");
const submitButton = document.getElementById("submitButton");
const signaturePad = document.getElementById("signaturePad");
const signaturePadFrame = document.getElementById("signaturePadFrame");
const clearSignatureButton = document.getElementById("clearSignature");
const regionField = document.getElementById("regionField");
const regionInputs = Array.from(document.querySelectorAll('input[name="region"]'));

const requiredFields = {
  visitor_name: document.getElementById("visitor_name"),
  organization_name: document.getElementById("organization_name"),
  contact_number: document.getElementById("contact_number"),
  mail_id: document.getElementById("mail_id"),
  purpose: document.getElementById("purpose"),
};

const optionalFields = {
  further_support: document.getElementById("further_support"),
};

let signatureContext;
let isDrawing = false;
let lastPoint = null;
let hasSignature = false;

const getSelectedRegion = () => {
  const selectedInput = regionInputs.find(input => input.checked);
  return selectedInput ? selectedInput.value.trim() : "";
};

const setRegionSelectionState = hasError => {
  regionField.classList.toggle("selection-missing", hasError);
};

const buildValidationMessage = ({ missingRequiredField, missingRegion, missingSignature }) => {
  const instructions = [];
  if (missingRequiredField) {
    instructions.push("complete all required fields");
  }
  if (missingRegion) {
    instructions.push("select one region");
  }
  if (missingSignature) {
    instructions.push("add your e-signature");
  }

  if (!instructions.length) {
    return "";
  }

  if (instructions.length === 1) {
    return `Please ${instructions[0]} before submitting.`;
  }

  const lastInstruction = instructions[instructions.length - 1];
  return `Please ${instructions.slice(0, -1).join(", ")} and ${lastInstruction} before submitting.`;
};

const getSignatureDataUrl = () => {
  if (!hasSignature) {
    return "";
  }

  const exportCanvas = document.createElement("canvas");
  const width = Math.max(Math.floor(signaturePad.clientWidth), 1);
  const height = Math.max(Math.floor(signaturePad.clientHeight), 1);
  const exportContext = exportCanvas.getContext("2d");

  exportCanvas.width = width;
  exportCanvas.height = height;
  exportContext.fillStyle = "#fffaf2";
  exportContext.fillRect(0, 0, width, height);
  exportContext.drawImage(signaturePad, 0, 0, width, height);

  return exportCanvas.toDataURL("image/png");
};

const configureSignaturePad = (savedImage = "") => {
  const ratio = Math.max(window.devicePixelRatio || 1, 1);
  const rect = signaturePadFrame.getBoundingClientRect();
  const width = Math.max(Math.floor(rect.width), 1);
  const height = Math.max(Math.floor(rect.height), 1);

  signaturePad.width = width * ratio;
  signaturePad.height = height * ratio;
  signaturePad.style.width = `${width}px`;
  signaturePad.style.height = `${height}px`;

  signatureContext = signaturePad.getContext("2d");
  signatureContext.setTransform(ratio, 0, 0, ratio, 0, 0);
  signatureContext.lineCap = "round";
  signatureContext.lineJoin = "round";
  signatureContext.lineWidth = 2.4;
  signatureContext.strokeStyle = "#1d2a24";
  signatureContext.fillStyle = "#fffaf2";
  signatureContext.fillRect(0, 0, width, height);

  if (savedImage) {
    const image = new Image();
    image.onload = () => {
      signatureContext.fillStyle = "#fffaf2";
      signatureContext.fillRect(0, 0, width, height);
      signatureContext.drawImage(image, 0, 0, width, height);
      hasSignature = true;
      signaturePadFrame.classList.remove("signature-missing");
    };
    image.src = savedImage;
  }
};

const setStatus = (type, text) => {
  statusBanner.hidden = false;
  statusBanner.className = `status-banner ${type}`;
  statusBanner.textContent = text;
};

const clearStatus = () => {
  statusBanner.hidden = true;
  statusBanner.className = "status-banner";
  statusBanner.textContent = "";
};

const formatApiError = (detail, fallbackMessage) => {
  if (!detail) {
    return fallbackMessage;
  }

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map(error => {
        if (typeof error === "string") {
          return error;
        }

        const field = Array.isArray(error.loc) ? error.loc[error.loc.length - 1] : "";
        const message = error.msg || fallbackMessage;
        return field ? `${field}: ${message}` : message;
      })
      .filter(Boolean);

    return messages.length ? messages.join(" ") : fallbackMessage;
  }

  if (typeof detail === "object") {
    return detail.message || detail.msg || fallbackMessage;
  }

  return fallbackMessage;
};

const getPayload = () => {
  return {
    ...Object.fromEntries(
      Object.entries(requiredFields).map(([key, element]) => [key, element.value.trim()])
    ),
    ...Object.fromEntries(
      Object.entries(optionalFields).map(([key, element]) => [key, element.value.trim()])
    ),
    region: getSelectedRegion(),
    signature: getSignatureDataUrl(),
  };
};

const focusFirstIncompleteField = ({ missingRegion, missingSignature }) => {
  for (const element of Object.values(requiredFields)) {
    if (!element.value.trim()) {
      element.focus();
      return;
    }
  }

  if (missingRegion) {
    regionInputs[0]?.focus();
    return;
  }

  if (missingSignature) {
    signaturePad.focus();
  }
};

const clearSignature = () => {
  hasSignature = false;
  isDrawing = false;
  lastPoint = null;
  signaturePadFrame.classList.remove("signature-missing");
  configureSignaturePad();
};

const resetForm = () => {
  form.reset();
  setRegionSelectionState(false);
  clearSignature();
};

const getPoint = event => {
  const rect = signaturePad.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
};

const beginStroke = event => {
  event.preventDefault();
  isDrawing = true;
  lastPoint = getPoint(event);
  hasSignature = true;
  signaturePadFrame.classList.remove("signature-missing");

  signatureContext.beginPath();
  signatureContext.moveTo(lastPoint.x, lastPoint.y);
  signatureContext.lineTo(lastPoint.x, lastPoint.y);
  signatureContext.stroke();

  if (typeof signaturePad.setPointerCapture === "function") {
    signaturePad.setPointerCapture(event.pointerId);
  }
};

const drawStroke = event => {
  if (!isDrawing) {
    return;
  }

  event.preventDefault();
  const point = getPoint(event);
  signatureContext.beginPath();
  signatureContext.moveTo(lastPoint.x, lastPoint.y);
  signatureContext.lineTo(point.x, point.y);
  signatureContext.stroke();
  lastPoint = point;
};

const endStroke = event => {
  if (!isDrawing) {
    return;
  }

  event.preventDefault();
  isDrawing = false;
  lastPoint = null;
  if (
    typeof signaturePad.releasePointerCapture === "function" &&
    typeof signaturePad.hasPointerCapture === "function" &&
    signaturePad.hasPointerCapture(event.pointerId)
  ) {
    signaturePad.releasePointerCapture(event.pointerId);
  }
};

form.addEventListener("submit", async event => {
  event.preventDefault();
  clearStatus();

  const payload = getPayload();
  const missingRequiredField = Object.values(requiredFields).some(element => !element.value.trim());
  const missingRegion = !payload.region;
  const missingSignature = !payload.signature;
  if (missingRequiredField || missingRegion || missingSignature) {
    setRegionSelectionState(missingRegion);

    if (missingSignature) {
      signaturePadFrame.classList.add("signature-missing");
    }

    setStatus(
      "error",
      buildValidationMessage({ missingRequiredField, missingRegion, missingSignature })
    );
    focusFirstIncompleteField({ missingRegion, missingSignature });
    return;
  }

  submitButton.disabled = true;
  submitButton.textContent = "Submitting...";

  try {
    const response = await fetch(`${API_BASE}/add-visitor`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json();
    if (!response.ok) {
      throw new Error(
        formatApiError(result.detail, "Your submission could not be completed.")
      );
    }

    setStatus(
      result.email_sent ? "success" : "warning",
      result.message || "Your details were submitted successfully."
    );
    resetForm();
  } catch (error) {
    setStatus("error", error.message || "Your submission could not be completed.");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Submit Details";
  }
});

clearSignatureButton.addEventListener("click", () => {
  clearSignature();
});

regionInputs.forEach(input => {
  input.addEventListener("change", event => {
    if (event.target.checked) {
      regionInputs.forEach(option => {
        if (option !== event.target) {
          option.checked = false;
        }
      });
      setRegionSelectionState(false);
    }
  });
});

signaturePad.addEventListener("pointerdown", beginStroke);
signaturePad.addEventListener("pointermove", drawStroke);
signaturePad.addEventListener("pointerup", endStroke);
signaturePad.addEventListener("pointerleave", endStroke);
signaturePad.addEventListener("pointercancel", endStroke);

window.addEventListener("resize", () => {
  const savedImage = getSignatureDataUrl();
  configureSignaturePad(savedImage);
});

configureSignaturePad();
