# Recuperação com TDE: o backup em outro servidor, sem e com o certificado

Gerado por `sqlserver/testar-restauracao-tde.ps1` em 2026-11-25T18:04:25Z (evidência: `sqlserver/evidence/parte3/restauracao-tde.json`).

O backup do SIGpAcademic (COPY_ONLY, com CHECKSUM; o banco de origem não muda) foi levado para um SQL Server 2022 novo e
descartável, como faria quem roubasse o arquivo. O certificado do TDE fica fora do banco e do Git (`segredos-locais/tde`),
protegido por senha no `.env.academic`.

| Verificação | Resultado |
|---|---|
| Tamanho do backup | 98.1 MB (SHA-256 568A71C8BECCA63A…) |
| TDE ligado na origem | sim |
| **Sem o certificado:** restaurou? | **não** (erro 33111: o servidor não tem o certificado que protege a chave do banco) |
| **Com o certificado e a senha dele:** restaurou? | **sim** |
| DBCC CHECKDB sem erros | sim |
| Linhas iguais às da origem | sim (Locais 3, Notas 100020, ItensNota 100020, Pagamentos 50010, Conciliacoes 100020, Eventos 1425) |
| TDE continua ligado no destino | sim |
| **Resultado** | **APROVADO** |

Conclusão: um backup roubado não serve para nada sem o certificado; com o certificado, a empresa recupera o banco íntegro.
Por isso o certificado e a senha dele ficam guardados juntos, num lugar seguro e separado dos backups.
