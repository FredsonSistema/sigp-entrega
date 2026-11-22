# Perfis e permissões — demonstração

Executado em 2026-11-22T03:50:11+00:00 num banco temporário (`demonstrar_perfis.py`).
✓ = permitido; ✗ = recusado (403 = perfil sem permissão; 401 = sem chave). 400/404/409 contam como permitido: a API aceitou o perfil e recusou só os dados de teste.

| Perfil | Ver locais | Ver caixa de notas recebidas | Criar local | Lançar nota | Decidir no SIG | Usar ordens de serviço | Fazer backup do banco | Administrar usuários |
|---|---|---|---|---|---|---|---|---|
| Administrador | ✓ 200 | ✓ 200 | ✓ 201 | ✓ 400 | ✓ 400 | ✓ 200 | ✓ 200 | ✓ 200 |
| Gerente (Maciel) | ✓ 200 | ✓ 200 | ✓ 201 | ✓ 400 | ✓ 400 | ✓ 200 | ✓ 200 | ✗ 403 |
| Operador (Jonata) | ✓ 200 | ✓ 200 | ✓ 201 | ✓ 400 | ✗ 403 | ✓ 200 | ✗ 403 | ✗ 403 |
| Leitura (auditoria) | ✓ 200 | ✓ 200 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 | ✗ 403 |
| Leitura + ordens de serviço (ajuste individual) | ✓ 200 | ✓ 200 | ✗ 403 | ✗ 403 | ✗ 403 | ✓ 200 | ✗ 403 | ✗ 403 |
| Sem chave | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 | ✗ 401 |

Auditoria: 33 registros, 15 recusas (quem, ação, funcionalidade, resultado). Ver `evidence/permissoes-perfis.json`.

Diferença para a Entrega 2: a versão daquela entrega (`sqlserver/evidence/parte2/demo-parte2-saida.txt`) mostrava "Sem chave" com 200 em Ver locais e Ver caixa de notas recebidas, e a leitura sem chave estava listada como pendente. Desde o login no servidor (commit `00f9f0f`), toda rota exige chave ou sessão, menos `/api/health`; `SIGP_EXIGIR_CHAVE_LEITURA=0` reabre a leitura só para diagnóstico. A linha "Sem chave" acima é a medida atual.
