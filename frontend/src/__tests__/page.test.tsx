import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/app/providers";
import { useChat } from "@/lib/chat";
import { useSession } from "@/lib/store";
import { installFakeServer, type FakeServer } from "./fake/server";

let srv: FakeServer;

beforeEach(() => {
  srv = installFakeServer();
  useSession.setState({ userId: "intern-anya", internPick: null , section: "plan" });
  useChat.getState().reset([]);
  // Node 24 подставляет свой пустой localStorage поверх jsdom — даём тестам честное хранилище в памяти
  const data = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, String(v)),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** Вкладка чата стажёра (чекпоинт 2: чаты разделены по темам). */
async function chatTab(name: string) {
  await act(async () => fireEvent.click(await screen.findByRole("tab", { name: new RegExp(`^${name}`) })));
}

function open(userId = "intern-anya") {
  useSession.setState({ userId, internPick: null , section: "plan" });
  return render(
    <Providers>
      <Home />
    </Providers>,
  );
}
const login = (id: string) => fireEvent.change(screen.getByLabelText("Войти как"), { target: { value: id } });
const click = (el: HTMLElement) => act(async () => fireEvent.click(el));
const week1 = () => screen.findByRole("region", { name: "Неделя 1" });

describe("экран «план + чат» на API", () => {
  it("бот пишет первым: день, прогресс, следующий шаг", async () => {
    open();
    expect(await screen.findByText(/2-й день стажировки/)).toBeTruthy();
    expect(screen.getByText(/Закрыто 1 из 11/)).toBeTruthy();
    expect(srv.calls.every((c) => c.user === "intern-anya")).toBe(true);
  });

  it("стажёр отмечает свой пункт — запрос на сервер и обновлённый план", async () => {
    open();
    const w1 = await week1();
    const before = within(w1).getAllByRole("button", { name: "Готово" }).length;
    await click(within(w1).getAllByRole("button", { name: "Готово" })[0]);
    await waitFor(() => expect(within(w1).queryAllByRole("button", { name: "Готово" })).toHaveLength(before - 1));
    expect(srv.calls.some((c) => c.method === "POST" && c.path.includes("/status"))).toBe(true);
  });

  it("ошибка отметки показывается у пункта", async () => {
    open();
    const w1 = await week1();
    srv.state.items.find((i) => i.id === "anya.w1.notes")!.owner_role = "mentor"; // сервер передумал
    const row = within(w1).getByText("Завести конспект встреч с наставником").closest("li")!;
    await click(within(row).getByRole("button", { name: "Готово" }));
    expect(await within(row).findByRole("alert")).toBeTruthy();
  });

  it("заявка: черновик → подтверждение → ждёт наставника → наставник одобряет", async () => {
    open();
    const w1 = await week1();
    const btns = within(w1).getAllByRole("button", { name: "Сделать за меня" });
    await click(btns[btns.length - 1]); // пространство команды
    expect(await screen.findByText(/Заявка на доступ · черновик/)).toBeTruthy();
    expect(srv.state.requests).toHaveLength(2); // без подтверждения ничего не создано
    await click(await screen.findByRole("button", { name: "Подтвердить" }));
    expect(await screen.findByText(/ушла на согласование: Пётр Волков/)).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/Ждём: Пётр Волков/)).toBeTruthy());

    act(() => login("mentor-petr"));
    await click(await screen.findByRole("button", { name: "Одобрить" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Ждут одобрения" })).toBeNull());
    expect(srv.state.items.find((i) => i.id === "anya.w1.access-team")?.status).toBe("done");
  });

  it("базовые доступы — в один клик, без второго подтверждения (чекпоинт 2)", async () => {
    open();
    const w1 = await week1();
    await click(within(w1).getAllByRole("button", { name: "Сделать за меня" })[0]);
    expect(await screen.findByText(/доступ к «Jira и Confluence» на чтение выдан/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Подтвердить" })).toBeNull();
    expect(srv.calls.some((c) => c.path.endsWith("/confirm"))).toBe(false);
  });

  it("повторная заявка — понятная ошибка", async () => {
    srv.state.requests.push({ ...srv.state.requests[0], id: "REQ-9", intern_id: "intern-anya", resource_id: "base-access" });
    open();
    const w1 = await week1();
    await click(within(w1).getAllByRole("button", { name: "Сделать за меня" })[0]);
    expect(await screen.findByText(/Не получилось: Заявка на этот ресурс уже есть/)).toBeTruthy();
  });

  it("отмена черновика ничего не создаёт", async () => {
    open();
    const all = within(await week1()).getAllByRole("button", { name: "Сделать за меня" });
    await click(all[all.length - 1]); // пространство команды — через черновик
    await click(await screen.findByRole("button", { name: "Отменить" }));
    expect(await screen.findByText(/ничего не отправлено/)).toBeTruthy();
    expect(srv.state.requests).toHaveLength(2);
  });

  it("наставник отклоняет с причиной", async () => {
    open("mentor-maria");
    await click(await screen.findByRole("button", { name: "Отклонить…" }));
    fireEvent.change(screen.getByPlaceholderText("Причина отказа"), { target: { value: "Сначала песочница" } });
    await click(screen.getByRole("button", { name: "Отклонить" }));
    expect(await screen.findByText(/Причина: Сначала песочница/)).toBeTruthy();
  });

  it("без ключа объяснение и подсказки строит сервер по пункту, источник — ссылкой", async () => {
    open();
    const title = "Запросить доступ в пространство команды и изучить его";
    const row = (await screen.findByText(title)).closest("li")!;
    await waitFor(() => expect(screen.getByText(/сценарный режим/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/^Из документа:/)).toBeTruthy();
    // Источник — кнопка: документ открывается в окне приложения, а не по внешней ссылке (проверка 12.11).
    expect(screen.getByRole("button", { name: "Первые дни стажёра" })).toBeTruthy();

    await click(screen.getByRole("button", { name: "Как это сделать по шагам?" }));
    expect(await screen.findByText(`По шагам: ${title}`)).toBeTruthy();
    const steps = srv.calls.filter((c) => c.path.includes("/explained")).at(-1)!;
    expect(steps.body).toEqual({ kind: "steps" });
    expect(steps.path).toContain("intern_id=intern-anya");
    // у ответа «по шагам» остаётся только вторая подсказка
    await click(screen.getAllByRole("button", { name: "К кому идти, если не получается?" }).at(-1)!);
    expect(await screen.findByText(`К кому идти: ${title}`)).toBeTruthy();
    expect(srv.calls.some((c) => c.path === "/chat")).toBe(false); // без ключа подсказки не уходят в поиск по всем документам
  });

  it("без ключа объяснение записывается в события и его можно оценить", async () => {
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(screen.getByText(/сценарный режим/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    await click(await screen.findByRole("button", { name: "Полезно" }));
    await waitFor(() => expect(srv.feedback).toEqual([{ answer_id: "ans_explain_anya.w1.notes", useful: true }]));
  });

  it("сбой записи события не мешает сценарному объяснению", async () => {
    srv.explainFails = true;
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(screen.getByText(/сценарный режим/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/Объясни пункт «Завести конспект/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Полезно" })).toBeNull();
  });

  it("сбой сервера на подсказке — сообщение, без выдуманного ответа", async () => {
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(screen.getByText(/сценарный режим/)).toBeTruthy());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    srv.explainFails = true;
    await click(await screen.findByRole("button", { name: "Как это сделать по шагам?" }));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
  });

  it("с моделью объяснение тоже строит сервер по пункту — не уходит в /chat (проверка 13.11)", async () => {
    srv.provider = "gigachat";
    open();
    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await waitFor(() => expect(srv.calls.some((c) => c.path === "/health")).toBe(true));
    await waitFor(() => expect(screen.queryByText(/сценарный режим/)).toBeNull());
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/^Из документа:/)).toBeTruthy();
    expect(screen.getByText("по документу пункта · глубина по карте навыков")).toBeTruthy();
    expect(srv.calls.some((c) => c.path.includes("/explained"))).toBe(true);
    expect(srv.calls.some((c) => c.path === "/chat")).toBe(false);
  });

  it("кнопки следующего шага в приветствии: сделать и объяснить (чекпоинт 2)", async () => {
    open();
    const hello = (await screen.findByText(/2-й день стажировки/)).parentElement!;
    expect(within(hello).getByRole("button", { name: "Объяснить" })).toBeTruthy();
    await click(within(hello).getByRole("button", { name: "Сделать за меня" }));
    expect((await screen.findByText(/на чтение выдан/)).textContent).toMatch(/Следующий шаг — «/);
  });

  it("Иван: кого ждём и напоминания при входе; «Напомнить позже»", async () => {
    open("intern-ivan");
    expect(await screen.findByText(/Ждём ответа \(Мария Орлова\)/)).toBeTruthy();
    await chatTab("Заявки");
    const reminder = (await screen.findByText(/ждёт. Напомнить наставнику/)).parentElement!;
    await click(within(reminder).getByRole("button", { name: "Напомнить позже" }));
    expect(await screen.findByText("Хорошо, напомню завтра.")).toBeTruthy();
    expect(srv.calls.some((c) => c.path.endsWith("/snooze"))).toBe(true);
  });

  it("зависшая заявка: «Написать наставнику» — готовый текст для копирования, бот сам не отправляет", async () => {
    open("intern-ivan");
    await chatTab("Заявки");
    const reminder = (await screen.findByText(/ждёт. Напомнить наставнику/)).parentElement!;
    await click(within(reminder).getByRole("button", { name: "Написать наставнику" }));
    expect(await screen.findByText(/получится посмотреть мою заявку REQ-\d+ \(пункт плана «/)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /^Скопировать/ }).length).toBeGreaterThan(0);
  });

  it("телефон: точка «новое» на вкладке «Чат», пока открыт план", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    expect(screen.getByLabelText("новые сообщения")).toBeTruthy();
    await click(screen.getByRole("tab", { name: /Чат/ }));
    expect(screen.queryByLabelText("новые сообщения")).toBeNull();
  });

  it("колокольчик (спека 301): число, одна кнопка «Открыть в чате», без «Готово»", async () => {
    open("intern-ivan");
    const bell = await screen.findByRole("button", { name: /Напоминания: \d/ });
    const count = Number(bell.getAttribute("aria-label")!.match(/\d+/)![0]);
    await click(bell);
    const dialog = screen.getByRole("dialog", { name: "Напоминания" });
    expect(within(dialog).getAllByRole("listitem")).toHaveLength(count);
    // Проверка 12.11: одна главная кнопка; просроченный пункт уходит сам, когда он закрыт
    expect(within(dialog).queryAllByRole("button", { name: "Готово" })).toHaveLength(0);
    const before = useChat.getState().messages.length;
    await click(within(dialog).getAllByRole("button", { name: "Открыть в чате" })[0]);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(useChat.getState().messages.length).toBe(before + 1));
    expect(srv.calls.some((c) => c.method === "POST" && c.path.endsWith("/done"))).toBe(false);
  });

  it("колокольчик: «Напомнить завтра», пусто, закрытие по Escape", async () => {
    open("intern-ivan");
    await click(await screen.findByRole("button", { name: /Напоминания: \d/ }));
    const items = within(screen.getByRole("dialog")).getAllByRole("listitem");
    for (const li of items) await click(within(li).getByRole("button", { name: "Напомнить завтра" }));
    expect(srv.calls.filter((c) => c.path.endsWith("/snooze"))).toHaveLength(items.length);
    expect(await screen.findByText(/Напоминаний нет — всё по плану/)).toBeTruthy();
    await act(async () => fireEvent.keyDown(document, { key: "Escape" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await click(screen.getByRole("button", { name: "Напоминаний нет" }));
    await act(async () => fireEvent.mouseDown(document.body));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("напоминание о просрочке ведёт к пункту", async () => {
    open("intern-ivan");
    await chatTab("Учёба");
    const reminder = (await screen.findByText(/прошёл срок/)).parentElement!;
    await click(within(reminder).getByRole("button", { name: "Объяснить" }));
    expect(await screen.findByText(/Объясни пункт «Завести конспект/)).toBeTruthy();
  });

  it("«Мой профиль»: стажёр видит, что бот о нём знает, без правки", async () => {
    srv.state.profiles[0].updated_by = "mentor-petr";
    open();
    await screen.findByText(/2-й день стажировки/);
    await click(screen.getByRole("tab", { name: "Мой профиль" }));
    expect(await screen.findByRole("heading", { name: "Мой профиль" })).toBeTruthy();
    expect(screen.getByText("Пётр Волков")).toBeTruthy();
    expect(screen.getByText("Ольга Новикова")).toBeTruthy();
    expect(screen.getByText("Git — новичок")).toBeTruthy();
    expect(screen.getByText("SQL — уверенно")).toBeTruthy();
    expect(screen.getByText(/Не влияет на права/)).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: /Git/ })).toBeNull(); // уровни стажёр не правит
    expect(screen.getByText("Последнее изменение: Пётр Волков")).toBeTruthy();
    await click(screen.getByRole("tab", { name: "Мой план" }));
    expect(await screen.findByRole("heading", { name: "Мой план" })).toBeTruthy();
  });

  it("итоги недели стажёру: при входе в первый день новой недели (Иван, день 8)", async () => {
    open("intern-ivan");
    expect(await screen.findByText(/Итоги недели 1 — только факты из плана/)).toBeTruthy();
    expect(screen.getByText(/Переходит на следующую неделю: «/)).toBeTruthy();
    expect(screen.getByText(/Эту же сводку видит наставник/)).toBeTruthy();
    expect(srv.calls.some((c) => c.path === "/plan/summary?intern_id=intern-ivan&week=1")).toBe(true);
  });

  it("итоги недели стажёру: «Следующий день» через конец недели (Аня 7 → 8)", async () => {
    srv.state.days["intern-anya"] = 7;
    open();
    await screen.findByText(/7-й день стажировки/);
    expect(screen.queryByText(/Итоги недели/)).toBeNull();
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText(/Итоги недели 1 — только факты из плана/)).toBeTruthy();
    expect(screen.getByText(/Закрыто: «/)).toBeTruthy();
  });

  it("сбой сводки недели не ломает приветствие", async () => {
    srv.state.days["intern-anya"] = 8;
    srv.summaryFails = true;
    open();
    expect(await screen.findByText(/8-й день стажировки/)).toBeTruthy();
    expect(screen.queryByText(/Итоги недели/)).toBeNull();
  });

  it("после обновления страницы: прошлая переписка, черновик и тот же пользователь (SPEC 9, D7)", async () => {
    srv.history["intern-ivan"] = [
      { id: "m1", role: "user", content: "Кто такой buddy?", sources: [], answer_id: null, scripted: false },
      { id: "m2", role: "assistant", content: "Buddy — наставник.", sources: [{ title: "Глоссарий стажировки", url: null }],
        answer_id: "ans_old", scripted: true },
    ];
    srv.actions.push({ id: "act_old", user_id: "intern-ivan", tool: "create_access_request", title: "Заявка: учебный Jira",
      params: { resource_id: "jira", level: "read", justification: "x" }, status: "pending", result: null, error: null });
    localStorage.setItem("ai-buddy-user", "intern-ivan");
    open();
    expect(await screen.findByText("Buddy — наставник.")).toBeTruthy();
    expect(screen.getByText("Кто такой buddy?")).toBeTruthy();
    expect(await screen.findByText(/8-й день стажировки/)).toBeTruthy(); // приветствие — после истории, под Иваном
    await chatTab("Заявки"); // неподтверждённый черновик — во вкладке «Заявки»
    expect(screen.getByText("Черновик ждёт твоего решения.")).toBeTruthy();
    const order = useChat.getState().messages.map((m) => m.content);
    expect(order.indexOf("Buddy — наставник.")).toBeLessThan(order.findIndex((c) => c.startsWith("Привет, Иван")));
  });

  it("выбор пользователя запоминается", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "mentor-petr" } });
    expect(localStorage.getItem("ai-buddy-user")).toBe("mentor-petr");
  });

  it("у наставника нет вкладки «Мой профиль»", async () => {
    open("mentor-petr");
    await screen.findByText(/План: Аня Смирнова/);
    expect(screen.queryByRole("tab", { name: "Мой профиль" })).toBeNull();
  });

  it("«Следующий день» и «Сброс»", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    await click(screen.getByRole("button", { name: "Следующий день" }));
    await waitFor(() => expect(srv.state.days["intern-anya"]).toBe(3));
    expect(await screen.findByText(/Зависших пунктов нет/)).toBeTruthy();
    await click(screen.getByRole("button", { name: "Сброс" }));
    expect(await screen.findByText(/2-й день стажировки/)).toBeTruthy();
  });

  it("код-слово демо-кнопок: спрашивает один раз, запоминает, сообщает об ошибке", async () => {
    srv.demoKey = "маяк";
    sessionStorage.clear();
    const prompt = vi.spyOn(window, "prompt");
    open();
    await screen.findByText(/2-й день стажировки/);

    prompt.mockReturnValueOnce(null);
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText("Без код-слова демо-кнопки на этом сайте не работают.")).toBeTruthy();

    prompt.mockReturnValueOnce("не то");
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText("Код-слово не подошло.")).toBeTruthy();
    expect(srv.state.days["intern-anya"]).toBe(2);

    prompt.mockReturnValueOnce(" маяк ");
    await click(screen.getByRole("button", { name: "Следующий день" }));
    await waitFor(() => expect(srv.state.days["intern-anya"]).toBe(3));
    await click(screen.getByRole("button", { name: "Сброс" }));
    expect(await screen.findByText(/2-й день стажировки/)).toBeTruthy();
    expect(prompt).toHaveBeenCalledTimes(3); // после верного код-слова больше не спрашивает
    prompt.mockRestore();
  });

  it("сбой демо-панели — сообщение", async () => {
    open();
    await screen.findByText(/2-й день стажировки/);
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await click(screen.getByRole("button", { name: "Следующий день" }));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await click(screen.getByRole("button", { name: "Сброс" }));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
  });

  it("куратор видит планы всех, но ничего не отмечает", async () => {
    open("curator-dmitry");
    await screen.findByText(/План: Аня Смирнова/);
    expect(screen.queryAllByRole("button", { name: "Готово" })).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("Стажёр"), { target: { value: "intern-ivan" } });
    expect(await screen.findByText("План: Иван Кузнецов")).toBeTruthy();
  });

  it("HR BP не видит планы", async () => {
    open("hrbp-elena");
    expect(await screen.findByText(/для твоей роли недоступны/)).toBeTruthy();
    expect(await screen.findByText(/Планы и профили стажёров тебе не показываю/)).toBeTruthy();
  });

  it("сервер недоступен — сообщение и «Повторить»", async () => {
    vi.mocked(globalThis.fetch).mockImplementation(async () => {
      throw new TypeError("Failed to fetch");
    });
    open();
    expect(await screen.findByText(/Не получилось загрузить план/, {}, { timeout: 4000 })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Повторить" }, { timeout: 4000 })).toBeTruthy();
  });

  it("сервер ответил не по контракту — понятная ошибка", async () => {
    srv.state.days["intern-anya"] = "два" as unknown as number;
    open();
    expect(await screen.findByText("Сервер ответил в неожиданном формате.", {}, { timeout: 4000 })).toBeTruthy();
  });

  it("переключатель «План / Чат» на узком экране", async () => {
    open();
    await click(screen.getByRole("tab", { name: "Чат" }));
    expect(screen.getByRole("tab", { name: "Чат" }).getAttribute("aria-selected")).toBe("true");
  });

  it("свободный вопрос: сбой → «Повторить» → ответ и черновик от модели", async () => {
    srv.chatReplies = ["fail", {
      reply: "Подготовил черновик",
      actions: [{ id: "act_x", user_id: "intern-anya", tool: "set_plan_item_status", title: "Пункт плана: сделано",
        params: {}, status: "pending", result: null, error: null }],
    }];
    open();
    await screen.findByText(/2-й день стажировки/);
    fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Как запустить сервис?" } });
    await act(async () => fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!));
    expect(await screen.findByText("Не получилось связаться с сервером.")).toBeTruthy();
    await click(screen.getByRole("button", { name: "Повторить" }));
    expect(await screen.findByText("Подготовил черновик")).toBeTruthy();
    expect(screen.getByText("Черновик действия")).toBeTruthy();
    expect(screen.getByText("Первые дни")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Первые дни" })).toBeNull(); // без адреса — без ссылки
  });

  it("ошибка модели показывает текст сервера; подсказка без ключа отвечает по пункту", async () => {
    srv.chatReplies = ["502"];
    open();
    await screen.findByText(/2-й день стажировки/);
    fireEvent.change(screen.getByLabelText("Сообщение"), { target: { value: "Привет" } });
    await act(async () => fireEvent.submit(screen.getByLabelText("Сообщение").closest("form")!));
    expect(await screen.findByText("Помощник временно недоступен.")).toBeTruthy();

    const row = (await screen.findByText("Завести конспект встреч с наставником")).closest("li")!;
    await click(within(row).getByRole("button", { name: "Объяснить" }));
    await click(await screen.findByRole("button", { name: "К кому идти, если не получается?" }));
    expect(await screen.findByText("К кому идти: Завести конспект встреч с наставником")).toBeTruthy();
  });
});
