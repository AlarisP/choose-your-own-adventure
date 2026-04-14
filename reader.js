const START_PAGE = 2;
const PAGES_DIR = 'output/cot-pages-ocr-v2/';

// ── Audio ──────────────────────────────────────────
const audio = document.getElementById('bg-audio');
let audioEnabled = localStorage.getItem('audioEnabled') !== 'false';
audio.volume = 0.4;

function hideAudioHint() {
  const hint = document.getElementById('audio-hint');
  if (hint) hint.style.display = 'none';
}

function tryPlayAudio() {
  if (!audioEnabled) return;
  audio.play().then(() => {
    hideAudioHint();
  }).catch(() => {
    // Browser blocked autoplay — start on first user interaction instead
    document.addEventListener('click', () => {
      if (audioEnabled) audio.play().catch(() => {});
      hideAudioHint();
    }, { once: true });
  });
}

function toggleAudio() {
  audioEnabled = !audioEnabled;
  localStorage.setItem('audioEnabled', audioEnabled);
  const btn = document.getElementById('audio-toggle');
  if (audioEnabled) {
    btn.textContent = '♪ Music: ON';
    audio.play().catch(() => {});
  } else {
    btn.textContent = '♪ Music: OFF';
    audio.pause();
  }
}

// Restore saved preference and attempt autoplay on load
if (!audioEnabled) {
  document.getElementById('audio-toggle').textContent = '♪ Music: OFF';
} else {
  tryPlayAudio();
}

let history = [];
let currentPage = START_PAGE;
let stepNumber = 1;

function pageFilename(num) {
  return PAGES_DIR + String(num).padStart(2, '0') + '-CoT.txt';
}

async function loadPage(pageNum) {
  const url = pageFilename(pageNum);

  let text;
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Not found');
    text = await response.text();
  } catch {
    document.getElementById('story-text').innerHTML =
      `<p class="error">Page ${pageNum} could not be loaded.</p>`;
    document.getElementById('choices').innerHTML = '';
    return;
  }

  currentPage = pageNum;
  document.getElementById('page-num').textContent = stepNumber;
  document.getElementById('back-btn').disabled = history.length === 0;
  document.getElementById('restart-btn').style.display = history.length === 0 ? 'none' : '';

  const { body, choices } = parsePage(text);
  const isTerminal = /the end/i.test(body);

  document.getElementById('story-text').innerHTML = formatText(body);
  renderChoices(choices, isTerminal);

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function parsePage(text) {
  // Remove the "Page N" header line at the top
  const lines = text.split('\n');
  if (/^Page \d+/.test(lines[0].trim())) {
    lines.shift();
  }

  const fullText = lines.join('\n');

  // Match choices: "If [label], tum/turn to page N."
  // OCR renders "turn" as "tum" sometimes
  const choiceRegex = /[IT]f ([^,]+),\s*\n?\s*t[ou](?:rn|m) to page (\d+)/gi;
  const choices = [];
  let match;

  while ((match = choiceRegex.exec(fullText)) !== null) {
    choices.push({
      label: match[1].trim(),
      page: parseInt(match[2], 10),
    });
  }

  // Strip the choice lines from displayed body text
  const body = fullText
    .replace(/[IT]f [^,]+,\s*\n?\s*t[ou](?:rn|m) to page \d+\.?/gi, '')
    .trim();

  return { body, choices };
}

function formatText(text) {
  // Convert double newlines to paragraph breaks, single newlines to spaces
  return text
    .split(/\n{2,}/)
    .map(para => `<p>${para.replace(/\n/g, ' ').trim()}</p>`)
    .filter(p => p !== '<p></p>')
    .join('');
}

function renderChoices(choices, isTerminal) {
  const container = document.getElementById('choices');
  container.innerHTML = '';

  if (isTerminal) {
    // Story ending — show "The End"
    const ending = document.createElement('div');
    ending.className = 'the-end';
    ending.innerHTML = '<p>THE END</p><p>Your adventure is over.</p>';
    container.appendChild(ending);
    return;
  }

  if (choices.length === 0) {
    // Page continues directly to the next page (no choices, not an ending)
    const btn = document.createElement('button');
    btn.className = 'choice-btn';
    btn.textContent = 'Continue →';
    btn.addEventListener('click', () => navigate(currentPage + 1));
    container.appendChild(btn);
    return;
  }

  choices.forEach(({ label, page }) => {
    const btn = document.createElement('button');
    btn.className = 'choice-btn';
    btn.textContent = `If ${label} → turn to page ${page}`;
    btn.addEventListener('click', () => navigate(page));
    container.appendChild(btn);
  });
}

function navigate(pageNum) {
  history.push(currentPage);
  stepNumber++;
  loadPage(pageNum);
}

function goBack() {
  if (history.length === 0) return;
  const prev = history.pop();
  stepNumber--;
  loadPage(prev);
}

function restart() {
  history = [];
  stepNumber = 1;
  loadPage(START_PAGE);
}

// Start on page 2
loadPage(START_PAGE);
