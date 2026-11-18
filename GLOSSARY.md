# ProcurePilot

Turns fragmented supplier information into comparable purchasing decisions and proves the money saved.

## Language

### Pricing

**VAT-inclusive quote**:
A supplier quote whose printed prices already contain VAT at a stated rate. Its prices are kept as printed; VAT is derived from them, never added on top.
_Avoid_: gross quote, tax-included pricing

**Net price**:
A price excluding VAT. Purchase orders and recorded savings are in net prices, with VAT shown separately as tax.
_Avoid_: pre-tax price, ex-VAT price

**Landed cost**:
What one quoted line would cost delivered: the price plus VAT, delivery and other charges, less discounts. Used to compare suppliers.
_Avoid_: total cost, all-in price

### Feedback and operations

**Feedback submission**:
One message a workspace member sends from the in-app feedback button, with optional category, screenshots and voice message. It belongs to one workspace, its status moves forward only (new, reviewed, resolved), and the submitter may withdraw it while it is new.
_Avoid_: ticket, support request, issue

**Platform operator**:
A ProcurePilot team member who may read and triage feedback from every workspace. Always also a member of some workspace, and an operator only while their live `platform_operator` record is active; the access covers feedback and nothing else. Not a workspace role.
_Avoid_: admin, super-user, staff role

**Demo workspace**:
A hosted workspace we run for demos and recordings, marked by `tenant.is_demo`. Its feedback is tagged demo so triage keeps it apart from pilot feedback.
_Avoid_: test tenant, sandbox
