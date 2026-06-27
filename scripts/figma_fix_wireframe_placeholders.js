// Запуск в Figma через MCP use_figma (fileKey: 5hKdtCYJEwgHqkKvto12aN)
// или вставить тело в use_figma после снятия rate limit.
// Цель: убрать «живые» данные и технический жаргон — оставить wireframe-плейсхолдеры.

await figma.loadFontAsync({ family: "Inter", style: "Regular" });
await figma.loadFontAsync({ family: "Inter", style: "Bold" });
await figma.loadFontAsync({ family: "Inter", style: "Semi Bold" });

const map = [
  ["Алгоритмы и структуры данных", "Название дисциплины"],
  ["Идентификатор: algo-2025", "Идентификатор курса"],
  ["Сортировка массива", "Задание 1"],
  ["Сортировка слиянием", "Черновик 1"],
  ["Теория графов (тест)", "Задание 2"],
  ["Объясните Big-O", "Задание 3"],
  ["Big-O нотация", "Черновик 2"],
  ["8.0 / 10", "балл / макс."],
  ["6.5 / 10", "балл / макс."],
  ["Средняя · 5/10", "средняя"],
  ["Лёгкая · 3/10", "лёгкая"],
  ["Сложная · 8/10", "сложная"],
  ["coding", "программирование"],
  ["mcq", "тест"],
  ["free_text", "текст"],
  ["pending_review", "на проверке"],
  ["Иванов Иван · @ivanov · группа «ИС-41»", "ФИО студента · учебная группа"],
  ["Прогноз перед экзаменом (черновик)", "Прогноз перед экзаменом"],
  ["public · по группе", "режим доступа"],
  ["156 отправок", "N отправок"],
  ["89 отправок", "N отправок"],
  ["42 отправки", "N отправок"],
  ["12 задач · 28 ключей · 71% зачёта", "N задач · N студентов · NN% зачёта"],
  ["Курсы / Алгоритмы и структуры данных", "Курсы / Название дисциплины"],
  ["☑ Лекция_01.pdf · 42 фрагмента", "☑ Лекция 1"],
  ["☑ Лекция_02.pdf · 38 фрагментов", "☑ Лекция 2"],
  ["Запустить генерацию (7 задач)", "Запустить генерацию"],
  ["• Сортировка слиянием · pending_review · coding", "• Черновик 1 · на проверке"],
  ["• Big-O нотация · pending_review · mcq", "• Черновик 2 · на проверке"],
  ["Алгоритмы", "Курс 1"],
  ["Базы данных", "Курс 2"],
  ["Машинное обучение", "Курс 3"],
  ["128", "N"],
  ["78%", "NN%"],
  ["72%", "NN%"],
  ["64%", "NN%"],
  ["71%", "NN%"],
  ["68%", "NN%"],
  ["54%", "NN%"],
  ["62%", "NN%"],
  ["24", "N"],
];

function walk(n, changed) {
  if (n.type === "TEXT") {
    let next = n.characters;
    for (const [from, to] of map) {
      if (next.includes(from)) next = next.split(from).join(to);
    }
    if (next !== n.characters) {
      changed.push({ from: n.characters, to: next });
      n.characters = next;
    }
  }
  if ("children" in n) for (const c of n.children) walk(c, changed);
}

const frames = figma.currentPage.findAll(
  (n) => n.type === "FRAME" && /^Рис\. \d+/.test(n.name),
);
const changed = [];
for (const f of frames) walk(f, changed);

// Блок ключа доступа на Рис. 8 (если ещё нет)
const courseFrame = frames.find((f) => f.name.startsWith("Рис. 8"));
let keyBlockAdded = false;
if (courseFrame && !courseFrame.findOne((n) => n.type === "TEXT" && n.characters.includes("Ключ доступа"))) {
  const stroke = [{ type: "SOLID", color: { r: 0, g: 0, b: 0 } }];
  const white = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
  const block = figma.createFrame();
  block.name = "Ключ доступа (условно)";
  block.layoutMode = "VERTICAL";
  block.primaryAxisSizingMode = "AUTO";
  block.counterAxisSizingMode = "AUTO";
  block.itemSpacing = 10;
  block.paddingTop = 16;
  block.paddingBottom = 16;
  block.paddingLeft = 16;
  block.paddingRight = 16;
  block.cornerRadius = 12;
  block.fills = white;
  block.strokes = stroke;
  block.strokeWeight = 1;
  block.dashPattern = [4, 4];
  const cap = figma.createText();
  cap.fontName = { family: "Inter", style: "Regular" };
  cap.fontSize = 13;
  cap.characters = "Ключ доступа (для закрытого курса)";
  cap.fills = [{ type: "SOLID", color: { r: 0, g: 0, b: 0 } }];
  cap.textAutoResize = "HEIGHT";
  block.appendChild(cap);
  cap.layoutSizingHorizontal = "FILL";
  const row = figma.createFrame();
  row.layoutMode = "HORIZONTAL";
  row.itemSpacing = 12;
  row.fills = [];
  row.strokes = [];
  block.appendChild(row);
  row.layoutSizingHorizontal = "FILL";
  const field = figma.createFrame();
  field.resize(280, 36);
  field.layoutSizingHorizontal = "FIXED";
  field.cornerRadius = 8;
  field.strokes = stroke;
  field.strokeWeight = 1;
  field.fills = white;
  row.appendChild(field);
  const ph = figma.createText();
  ph.fontName = { family: "Inter", style: "Regular" };
  ph.fontSize = 13;
  ph.characters = "ключ доступа";
  ph.fills = [{ type: "SOLID", color: { r: 0.5, g: 0.5, b: 0.5 } }];
  field.appendChild(ph);
  ph.x = 12;
  ph.y = 10;
  const btn = figma.createFrame();
  btn.layoutMode = "HORIZONTAL";
  btn.paddingTop = 8;
  btn.paddingBottom = 8;
  btn.paddingLeft = 14;
  btn.paddingRight = 14;
  btn.cornerRadius = 8;
  btn.strokes = stroke;
  btn.strokeWeight = 1;
  btn.fills = white;
  row.appendChild(btn);
  const bt = figma.createText();
  bt.fontName = { family: "Inter", style: "Semi Bold" };
  bt.fontSize = 13;
  bt.characters = "Применить";
  bt.fills = [{ type: "SOLID", color: { r: 0, g: 0, b: 0 } }];
  btn.appendChild(bt);
  courseFrame.appendChild(block);
  block.layoutSizingHorizontal = "FILL";
  keyBlockAdded = true;
}

return { frames: frames.map((f) => f.name), changedCount: changed.length, keyBlockAdded };
