# Fluxo do n8n exportado: nenhum segredo no arquivo

Verificador: [`verificar_segredos_n8n.py`](verificar_segredos_n8n.py) · Evidência: [`../sqlserver/evidence/parte3/segredos-n8n.json`](../sqlserver/evidence/parte3/segredos-n8n.json)

## O que é verificado

1. **Todos os arquivos de workflow rastreados no Git**: o fluxo acadêmico ([`n8n_workflow_academic_ai.json`](n8n_workflow_academic_ai.json)) e os fluxos do SIGp na raiz e em `n8n/`.
2. **Todos os workflows do n8n em execução**, com a opção `--ao-vivo`. É uma exportação temporária (`n8n export:workflow --all`), apagada no fim, que pega o que está publicado de verdade, inclusive o que ainda não foi salvo no repositório.

As regras:

| Tipo | Regra |
|---|---|
| FALHA | O **valor real** de um segredo dos `.env` aparece no arquivo. O verificador procura o próprio valor e nunca o imprime. |
| FALHA | Cabeçalho ou parâmetro de autenticação (Authorization, X-API-Key, apikey, token, senha…) com valor literal em vez de `{{ $env… }}` ou credencial do n8n |
| FALHA | Padrões de chave conhecidos: Bearer literal, JWT, chave privada, chaves de Google, GitHub, OpenAI e AWS, token de bot do Telegram, chave de integração do SIGp |
| FALHA | Bloco `credentials` com algo além de `id` e `name`. A credencial em si fica no banco do n8n, criptografada, e não vai para o arquivo. |
| FALHA | `pinData` com dados: execuções gravadas no arquivo podem trazer e-mails e notas reais |
| AVISO | Texto de exemplo num campo de autenticação (`COLE_AQUI_...`) |
| AVISO | Endereço de e-mail: é dado pessoal, não segredo, mas o repositório é público |

## Resultado

**APROVADO**: os 7 segredos dos arquivos `.env` foram procurados em 21 arquivos do repositório e em 14 workflows do n8n
em execução, sem nenhuma falha.

| Origem | Arquivos | Falhas | Avisos |
|---|---|---|---|
| Repositório | 21 | 0 | 1: um endereço Gmail no filtro de busca do WF-08, junto com os domínios dos provedores |
| n8n em execução | 14 | 0 | 14: o e-mail da conta dona do n8n, que a exportação grava nos metadados. Esses arquivos são temporários e não vão para o Git. |

Como os fluxos se mantêm sem segredo:
- **Chaves e endereços** vêm de variáveis de ambiente do container do n8n, por exemplo `={{ $env.SIGP_ACADEMIC_AI_KEY }}` no fluxo acadêmico. Os valores ficam no `.env`, que é ignorado pelo Git.
- **Credenciais de serviços** (Gmail, Telegram) são credenciais do n8n. O arquivo exportado só tem o `id` e o `name` delas.

## Histórico

A primeira execução **reprovou** o `n8n_workflow_contas_provedores.json`. O nó "Notificar WhatsApp (Evolution API)" tinha
valor literal no cabeçalho `apikey`. Era texto de exemplo (`COLE_AQUI_A_APIKEY_EVOLUTION`), não uma chave, e o workflow
não está ativo. Mas o modelo convidava a colar a chave no nó, e ela vazaria na próxima exportação.

Correções:
- O nó passou a usar `{{ $env.SIGP_WHATSAPP_URL }}`, `{{ $env.SIGP_WHATSAPP_APIKEY }}` e `{{ $env.SIGP_WHATSAPP_NUMERO }}`, como os nós de WhatsApp do WF-05, do WF-06 e do WF-99.
- O verificador passou a tratar texto de exemplo como AVISO, e não como FALHA.

Reteste: APROVADO. Ver [`../historico-evolucao.md`](../historico-evolucao.md), H-25.

## Como rodar

Na raiz do projeto, com o n8n no ar:

```powershell
.venv-1\Scripts\python.exe docs/entrega-academica/ia/verificar_segredos_n8n.py --ao-vivo
```

Sem `--ao-vivo`, o verificador olha só os arquivos do repositório. Ele sai com código 1 se houver falha, então pode rodar
antes de cada commit que mexa num workflow.
