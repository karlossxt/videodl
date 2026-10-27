/* Transcripción de audio o vídeo a texto.
   El archivo se sube al servidor, se extrae el audio con ffmpeg y se pasa a
   Whisper (faster-whisper). El resultado se descarga en TXT, SRT o VTT. */
(function () {
  "use strict";

  const {
    $,
    t,
    showToast,
    showError,
    clearError,
    formatBytes,
    fmtClock,
    fetchWithTimeout,
    errorFromResponse,
    pollJob,
    linkDropzone,
    saveResponseAsFile,
  } = window.VD;

  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const fileCard = $("file-card");
  const fileName = $("file-name");
  const fileMeta = $("file-meta");
  const processBtn = $("process-btn");
  const actionHint = $("action-hint");
  const progress = $("progress");
  const progressFill = $("progress-fill");
  const progressBar = $("progress-bar");
  const progressPercent = $("progress-percent");
  const progressMessage = $("progress-message");
  const cancelBtn = $("cancel-btn");
  const result = $("result");
  const transcript = $("transcript-text");
  const serviceNote = $("service-note");

  let selectedFile = null;
  let jobId = null;
  let available = true;
  let maxUploadMb = 100;
  let maxSeconds = 1800;
  let processing = false;

  const LANGUAGE_NAMES = {
    es: t("transcribe.lang.es", "Español"),
    en: t("transcribe.lang.en", "Inglés"),
    pt: t("transcribe.lang.pt", "Portugués"),
    fr: t("transcribe.lang.fr", "Francés"),
    de: t("transcribe.lang.de", "Alemán"),
    it: t("transcribe.lang.it", "Italiano"),
    ca: t("transcribe.lang.ca", "Catalán"),
    gl: t("transcribe.lang.gl", "Gallego"),
    eu: t("transcribe.lang.eu", "Euskera"),
    ru: t("transcribe.lang.ru", "Ruso"),
    zh: t("transcribe.lang.zh", "Chino"),
    ja: t("transcribe.lang.ja", "Japonés"),
    ar: t("transcribe.lang.ar", "Árabe"),
    hi: t("transcribe.lang.hi", "Hindi"),
  };

  $("error-close").addEventListener("click", clearError);

  // -------------------------------------------------------------------------
  // Capacidades del servidor
  // -------------------------------------------------------------------------

  async function loadOptions() {
    try {
      const res = await fetchWithTimeout("/api/transcribe/options", {}, 15000);
      if (!res.ok) return;
      const data = await res.json();
      available = data.available !== false;
      maxUploadMb = Number(data.max_upload_mb) || maxUploadMb;
      maxSeconds = Number(data.max_seconds) || maxSeconds;
      const minutes = Math.max(1, Math.round(maxSeconds / 60));
      $("limit-hint").textContent = t(
        "transcribe.limitHint",
        `Audio o vídeo · hasta ${maxUploadMb} MB y ${minutes} min`,
        { mb: maxUploadMb, minutes }
      );
      $("limit-hint-2").textContent = `${maxUploadMb} MB`;

      if (!available) {
        serviceNote.textContent = t(
          "transcribe.unavailableNote",
          "La transcripción no está activada en este servidor ahora mismo. Puedes seguir usando el resto de herramientas de FasTools."
        );
        serviceNote.classList.remove("hidden");
        processBtn.disabled = true;
        actionHint.textContent = t(
          "transcribe.unavailable",
          "Transcripción no disponible."
        );
      }
    } catch {
      // Si el endpoint falla, se dejan los límites por defecto y se intenta igual.
    }
  }

  // -------------------------------------------------------------------------
  // Archivo
  // -------------------------------------------------------------------------

  function setFile(file) {
    clearError();
    if (!file) return;

    if (file.size > maxUploadMb * 1024 * 1024) {
      showError(
        t(
          "transcribe.tooLarge",
          `El archivo supera el límite de ${maxUploadMb} MB.`,
          { max: maxUploadMb }
        )
      );
      return;
    }

    selectedFile = file;
    fileName.textContent = file.name || t("transcribe.audioFallback", "audio");
    fileMeta.textContent = t(
      "transcribe.fileMeta",
      `${formatBytes(file.size)} · ${file.type || "formato desconocido"}`,
      {
        size: formatBytes(file.size),
        type: file.type || t("transcribe.unknownFormat", "formato desconocido"),
      }
    );
    fileCard.classList.remove("hidden");
    dropzone.classList.add("hidden");
    processBtn.disabled = !available;
    actionHint.textContent = available
      ? t(
          "transcribe.ready",
          "Listo para transcribir. El audio se sube al servidor y se borra al terminar."
        )
      : t("transcribe.unavailable", "Transcripción no disponible.");
  }

  function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    fileCard.classList.add("hidden");
    dropzone.classList.remove("hidden");
    processBtn.disabled = true;
    actionHint.textContent = t(
      "transcribe.chooseFile",
      "Elige un archivo para activar la transcripción."
    );
    clearError();
  }

  linkDropzone(dropzone, fileInput, setFile);
  $("file-clear").addEventListener("click", clearFile);

  // -------------------------------------------------------------------------
  // Progreso
  // -------------------------------------------------------------------------

  function showProgress(text) {
    progress.classList.remove("hidden");
    result.classList.add("hidden");
    progressMessage.textContent = text || t("transcribe.preparing", "Preparando…");
    progressPercent.textContent = "0 %";
    progressFill.style.width = "0%";
    progressFill.classList.add("indeterminate");
    progressBar.setAttribute("aria-valuenow", "0");
    cancelBtn.disabled = false;
  }

  function hideProgress() {
    progress.classList.add("hidden");
    progressFill.classList.remove("indeterminate");
  }

  function updateProgress(job) {
    if (!job) return;
    const percent = Math.max(0, Math.min(100, Number(job.percent) || 0));
    const working = ["pending", "probing", "extracting", "transcribing"].includes(job.status);

    if (working && percent <= 0) {
      progressFill.classList.add("indeterminate");
    } else {
      progressFill.classList.remove("indeterminate");
      progressFill.style.width = `${percent}%`;
    }
    progressPercent.textContent = `${Math.round(percent)} %`;
    progressBar.setAttribute("aria-valuenow", String(Math.round(percent)));
    progressMessage.textContent = t(
      "transcribe.processing",
      job.message || "Procesando…"
    );
  }

  // -------------------------------------------------------------------------
  // Transcripción
  // -------------------------------------------------------------------------

  async function startTranscription() {
    if (!selectedFile || !available || processing) return;
    processing = true;
    clearError();
    result.classList.add("hidden");
    processBtn.disabled = true;
    processBtn.textContent = t(
      "transcribe.transcribingButton",
      "⏳ Transcribiendo…"
    );
    actionHint.textContent = t(
      "transcribe.keepOpen",
      "No cierres esta pestaña: el progreso se actualiza solo."
    );
    showProgress(t("transcribe.uploading", "Subiendo el archivo…"));

    try {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("language", $("language").value);

      // Subir es la parte lenta en archivos grandes; la transcripción se sondea aparte.
      const res = await fetchWithTimeout(
        "/api/transcribe",
        { method: "POST", body: form },
        180000
      );
      if (!res.ok) {
        throw await errorFromResponse(
          res,
          t("transcribe.startFailed", "No se pudo iniciar la transcripción.")
        );
      }
      const data = await res.json();
      jobId = data.id;
      showProgress(t("transcribe.queued", "En cola…"));

      const job = await pollJob({
        fetcher: async () => {
          const statusRes = await fetchWithTimeout(
            `/api/transcribe/${jobId}`,
            {},
            20000
          );
          if (!statusRes.ok) {
            throw await errorFromResponse(
              statusRes,
              t("transcribe.statusFailed", "No se pudo consultar el trabajo.")
            );
          }
          return statusRes.json();
        },
        onUpdate: updateProgress,
        intervalMs: 1200,
        timeoutMs: 60 * 60 * 1000,
      });

      if (job.status === "finished") {
        showResult(job);
      } else if (job.status === "cancelled") {
        hideProgress();
        showToast(t("transcribe.cancelled", "Transcripción cancelada"));
        actionHint.textContent = t(
          "transcribe.tryAnother",
          "Puedes probar con otro archivo."
        );
      } else {
        throw new Error(
          t(
            "transcribe.failed",
            job.error || "No se pudo transcribir el audio."
          )
        );
      }
    } catch (err) {
      hideProgress();
      const message = t(
        "transcribe.failed",
        err.message || "No se pudo transcribir el audio."
      );
      showError(message);
      actionHint.textContent = t(
        "transcribe.checkFile",
        "Revisa el archivo e inténtalo de nuevo."
      );
    } finally {
      processing = false;
      processBtn.disabled = !selectedFile || !available;
      processBtn.textContent = t(
        "transcribe.transcribeButton",
        "📝 Transcribir audio"
      );
    }
  }

  function showResult(job) {
    hideProgress();
    result.classList.remove("hidden");

    const text = job.text || "";
    transcript.value = text;
    const words = text.trim() ? text.trim().split(/\s+/).filter(Boolean).length : 0;
    $("stat-words").textContent = String(words);
    $("stat-chars").textContent = String(text.length);
    $("stat-duration").textContent = job.duration ? fmtClock(job.duration) : "—";
    const lang =
      job.language && job.language !== "desconocido"
        ? LANGUAGE_NAMES[job.language] || job.language.toUpperCase()
        : t("transcribe.languageUnknown", "Idioma no detectado");
    $("stat-language").textContent = lang;

    actionHint.textContent = t(
      "transcribe.readyResult",
      "Transcripción lista. Revisa el texto antes de descargarlo."
    );
    result.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // -------------------------------------------------------------------------
  // Descargas y acciones
  // -------------------------------------------------------------------------

  async function downloadFormat(format) {
    if (!jobId) return;
    try {
      const res = await fetchWithTimeout(
        `/api/transcribe/${jobId}/file?format=${encodeURIComponent(format)}`,
        {},
        30000
      );
      if (!res.ok) {
        throw await errorFromResponse(
          res,
          t("transcribe.downloadFailed", "No se pudo descargar la transcripción.")
        );
      }
      await saveResponseAsFile(
        res,
        `${t("transcribe.downloadName", "transcripcion")}.${format}`
      );
      showToast(
        t("transcribe.downloading", `Descargando ${format.toUpperCase()}…`, {
          format: format.toUpperCase(),
        })
      );
    } catch (err) {
      showError(
        err.message ||
          t("transcribe.downloadFailed", "No se pudo descargar la transcripción.")
      );
    }
  }

  $("process-btn").addEventListener("click", startTranscription);
  $("download-txt").addEventListener("click", () => downloadFormat("txt"));
  $("download-srt").addEventListener("click", () => downloadFormat("srt"));
  $("download-vtt").addEventListener("click", () => downloadFormat("vtt"));

  $("copy-btn").addEventListener("click", async () => {
    const text = transcript.value;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showToast(t("transcribe.copied", "Texto copiado"));
    } catch {
      transcript.select();
      document.execCommand("copy");
      showToast(t("transcribe.copied", "Texto copiado"));
    }
  });

  $("cancel-btn").addEventListener("click", async () => {
    if (!jobId) return;
    cancelBtn.disabled = true;
    try {
      const res = await fetchWithTimeout(
        `/api/transcribe/${jobId}/cancel`,
        { method: "POST" },
        15000
      );
      if (!res.ok) {
        throw await errorFromResponse(
          res,
          t("transcribe.cancelFailed", "No se pudo cancelar el trabajo.")
        );
      }
      progressMessage.textContent = t("transcribe.cancelling", "Cancelando…");
    } catch (err) {
      showError(
        err.message ||
          t("transcribe.cancelFailed", "No se pudo cancelar el trabajo.")
      );
      cancelBtn.disabled = false;
    }
  });

  $("again-btn").addEventListener("click", () => {
    jobId = null;
    result.classList.add("hidden");
    hideProgress();
    clearFile();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // Estado inicial.
  loadOptions();
})();
