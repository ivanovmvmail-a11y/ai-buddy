import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RichText } from "@/components/RichText";

describe("RichText: разметка в ответах модели (проверка 13.11)", () => {
  it("блок кода, жирный и код в строке — без звёздочек и обратных кавычек", () => {
    const { container } = render(
      <RichText text={"Создай ветку:\n```bash\ngit checkout -b feature\n```\nПотом **открой PR** и запусти `make test`."} />,
    );
    expect(container.querySelector("pre")?.textContent).toBe("git checkout -b feature");
    expect(screen.getByText("открой PR").tagName).toBe("STRONG");
    expect(screen.getByText("make test").tagName).toBe("CODE");
    expect(container.textContent).not.toContain("```");
    expect(container.textContent).not.toContain("**");
  });

  it("незакрытый блок и обычный текст не ломаются", () => {
    const { container } = render(<RichText text={"Шаг 1\n```bash\ngit push"} />);
    expect(container.textContent).toContain("git push");
    expect(container.querySelector("pre")).toBeNull();
  });
});
