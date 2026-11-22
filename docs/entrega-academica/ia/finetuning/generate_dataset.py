from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "dataset.jsonl"

SYSTEM = (
    "Classifique cobranças usando somente as evidências estruturadas fornecidas. "
    "Não aprove pagamentos. Se a evidência for insuficiente, responda REVISAR. "
    "Retorne somente JSON: {\"classification\":\"CONTRATADO|DIVERGENTE|REVISAR\"}."
)


def build_examples() -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []

    contracted_services = [
        ("link principal fibra", 450.00),
        ("link de contingência", 280.00),
        ("IP fixo adicional", 35.00),
        ("suporte técnico mensal", 120.00),
        ("hospedagem gerenciada", 199.90),
        ("licença de monitoramento", 89.00),
    ]
    locations = ["Agência Centro", "Garagem Sul", "Unidade Leste", "Posto Norte", "Escritório Alfa"]
    providers = ["Conecta Horizonte", "Rede Exemplo", "Serviços Nuvem Fictícios", "Telecom Aurora"]

    for index in range(40):
        service, amount = contracted_services[index % len(contracted_services)]
        location = locations[(index // 2) % len(locations)]
        provider = providers[(index // 3) % len(providers)]
        billed = amount
        examples.append({
            "id": f"FT-C-{index + 1:03}",
            "split": _split(index, "CONTRATADO"),
            "user": (
                f"Cobrança: {service}, R$ {billed:.2f}. Provedor: {provider}. "
                f"Unidade: {location}. Evidência: contrato vigente inclui exatamente "
                f"{service} por R$ {amount:.2f} ao mês. Qual é a classificação?"
            ),
            "classification": "CONTRATADO",
        })

    for index in range(40):
        service, amount = contracted_services[index % len(contracted_services)]
        location = locations[(index // 2) % len(locations)]
        provider = providers[(index // 3) % len(providers)]
        if index % 2:
            billed = amount + 17.50 + index
            evidence = f"Contrato vigente prevê {service} por R$ {amount:.2f} ao mês."
            description = service
        else:
            billed = 35.00 + index
            description = f"serviço premium não previsto {index + 1}"
            evidence = f"Contrato vigente exclui expressamente {description}."
        examples.append({
            "id": f"FT-D-{index + 1:03}",
            "split": _split(index, "DIVERGENTE"),
            "user": (
                f"Cobrança: {description}, R$ {billed:.2f}. Provedor: {provider}. "
                f"Unidade: {location}. Evidência: {evidence} Qual é a classificação?"
            ),
            "classification": "DIVERGENTE",
        })

    review_scenarios = [
        ("serviço de suporte", "não há contrato nem ordem de serviço disponíveis"),
        ("taxa de ativação", "documento recebido sem aditivo ou autorização correspondente"),
        ("pacote adicional", "a evidência não confirma escopo, vigência ou valor"),
        ("serviço emergencial", "não foi localizada aprovação do responsável"),
        ("licença extra", "há descrição incompleta e nenhuma fonte contratual aplicável"),
        ("visita técnica", "a documentação disponível não permite confirmar a cobrança"),
    ]
    for index in range(40):
        service, evidence = review_scenarios[index % len(review_scenarios)]
        amount = 75.00 + index * 3.25
        location = locations[(index // 2) % len(locations)]
        provider = providers[(index // 3) % len(providers)]
        examples.append({
            "id": f"FT-R-{index + 1:03}",
            "split": _split(index, "REVISAR"),
            "user": (
                f"Cobrança: {service}, R$ {amount:.2f}. Provedor: {provider}. "
                f"Unidade: {location}. Evidência: {evidence}. Qual é a classificação?"
            ),
            "classification": "REVISAR",
        })

    return examples


def _split(index: int, label: str) -> str:
    if label == "REVISAR":
        train_end, validation_end = 26, 32
    else:
        train_end, validation_end = 27, 34
    if index < train_end:
        return "train"
    if index < validation_end:
        return "validation"
    return "test"


def main() -> None:
    examples = build_examples()
    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in examples),
        encoding="utf-8",
    )
    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    counts = {
        split: sum(row["split"] == split for row in examples)
        for split in ("train", "validation", "test")
    }
    print(json.dumps({"path": str(OUTPUT), "sha256": digest, "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
