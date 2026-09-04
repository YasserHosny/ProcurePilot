import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../core/api/api.service';
import type {
  Branch,
  BranchCreate,
  BranchList,
  BranchRoleAssignment,
  BranchRoleAssignmentCreate,
  BranchUpdate,
  Budget,
  BudgetCreate,
  BudgetCreated,
  BudgetList,
  BudgetPeriod,
  BudgetScope,
  CostCentre,
  CostCentreCreate,
  CostCentreList,
  CostCentreUpdate,
  OrphanReason,
} from '../../core/api/models';

export type {
  Branch,
  BranchCreate,
  BranchList,
  BranchRoleAssignment,
  BranchRoleAssignmentCreate,
  BranchUpdate,
  Budget,
  BudgetCreate,
  BudgetCreated,
  BudgetList,
  BudgetPeriod,
  BudgetScope,
  CostCentre,
  CostCentreCreate,
  CostCentreList,
  CostCentreUpdate,
  OrphanReason,
};

@Injectable({ providedIn: 'root' })
export class OrganisationApiService {
  private readonly api = inject(ApiService);

  listBranches(params?: {
    is_active?: boolean;
    cursor?: string;
    limit?: number;
  }): Observable<BranchList> {
    return this.api.listBranches(params);
  }

  createBranch(body: BranchCreate, idempotencyKey?: string): Observable<Branch> {
    return this.api.createBranch(body, idempotencyKey);
  }

  updateBranch(branchId: string, body: BranchUpdate): Observable<Branch> {
    return this.api.updateBranch(branchId, body);
  }

  listCostCentres(params?: {
    branch_id?: string;
    is_archived?: boolean;
    cursor?: string;
    limit?: number;
  }): Observable<CostCentreList> {
    return this.api.listCostCentres(params);
  }

  createCostCentre(body: CostCentreCreate, idempotencyKey?: string): Observable<CostCentre> {
    return this.api.createCostCentre(body, idempotencyKey);
  }

  updateCostCentre(costCentreId: string, body: CostCentreUpdate): Observable<CostCentre> {
    return this.api.updateCostCentre(costCentreId, body);
  }

  listBudgets(params?: {
    scope?: BudgetScope;
    branch_id?: string;
    cost_centre_id?: string;
    cursor?: string;
    limit?: number;
  }): Observable<BudgetList> {
    return this.api.listBudgets(params);
  }

  createBudget(body: BudgetCreate, idempotencyKey?: string): Observable<BudgetCreated> {
    return this.api.createBudget(body, idempotencyKey);
  }

  createBranchRoleAssignment(
    body: BranchRoleAssignmentCreate,
    idempotencyKey?: string,
  ): Observable<BranchRoleAssignment> {
    return this.api.createBranchRoleAssignment(body, idempotencyKey);
  }

  removeBranchRoleAssignment(assignmentId: string): Observable<void> {
    return this.api.removeBranchRoleAssignment(assignmentId);
  }
}
