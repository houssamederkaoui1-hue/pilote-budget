import { useMemo, useState } from "react";

import { ArchiveIcon, CategoriesIcon, PencilIcon, PlusIcon, TrashIcon } from "../components/icons";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Field, Input, Select, TextArea } from "../components/ui/Form";
import { Modal } from "../components/ui/Modal";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/States";
import { useApi } from "../hooks/useApi";
import { useMutation, errorMessage } from "../hooks/useMutation";
import { apiDelete, apiPatch, apiPost } from "../lib/api";
import type { Category, CategoryType } from "../types/api";
import styles from "./CategoriesPage.module.css";

export function CategoriesPage() {
  const categories = useApi<Category[]>("/categories");
  const [typeFilter, setTypeFilter] = useState<CategoryType>("expense");
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Category | null>(null);

  const listed = categories.data ?? [];
  const filtered = useMemo(
    () =>
      listed.filter(
        (category) =>
          category.type === typeFilter && (showArchived ? true : category.active),
      ),
    [listed, typeFilter, showArchived],
  );

  const remove = useMutation((category: Category) => apiDelete(`/categories/${category.id}`));
  const toggle = useMutation((category: Category) =>
    apiPatch<Category>(`/categories/${category.id}`, { active: !category.active }),
  );

  const runToggle = async (category: Category) => {
    try {
      await toggle.mutate(category);
      categories.reload();
    } catch {
      // surfaced below
    }
  };

  const runDelete = async (category: Category) => {
    if (!window.confirm(`Delete category "${category.name}"? Used categories must be archived instead.`)) return;
    try {
      await remove.mutate(category);
      categories.reload();
    } catch {
      // surfaced below
    }
  };

  const onSaved = () => {
    setCreating(false);
    setEditing(null);
    categories.reload();
  };

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Overview</div>
          <h1>Categories</h1>
          <p className="page-header__subtitle">
            Income and expense categories keep your ledger tidy and enable category analysis.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <PlusIcon size={15} />
          Add category
        </Button>
      </div>

      {(remove.error || toggle.error) && (
        <div className={styles.inlineError} role="alert">
          {remove.error || toggle.error}
        </div>
      )}

      <Card
        title={`${typeFilter === "expense" ? "Expense" : "Income"} categories`}
        subtitle={
          categories.data
            ? `${filtered.length} active ${showArchived ? "(incl. archived) " : ""}of ${listed.length} total`
            : undefined
        }
        action={
          <div className={styles.cardActions}>
            <div className="tabs">
              <button
                type="button"
                className={typeFilter === "expense" ? "active" : ""}
                onClick={() => setTypeFilter("expense")}
              >
                Expense
              </button>
              <button
                type="button"
                className={typeFilter === "income" ? "active" : ""}
                onClick={() => setTypeFilter("income")}
              >
                Income
              </button>
            </div>
            <div className="tabs">
              <button
                type="button"
                className={!showArchived ? "active" : ""}
                onClick={() => setShowArchived(false)}
              >
                Active
              </button>
              <button
                type="button"
                className={showArchived ? "active" : ""}
                onClick={() => setShowArchived(true)}
              >
                All
              </button>
            </div>
          </div>
        }
      >
        {categories.loading && <LoadingState label="Loading categories…" />}
        {!categories.loading && categories.error && (
          <ErrorState message={categories.error} onRetry={categories.reload} />
        )}
        {!categories.loading && !categories.error && filtered.length === 0 && (
          <EmptyState
            icon={<CategoriesIcon size={20} />}
            title="No categories here"
            description={
              categories.data?.length
                ? "Nothing matches the current filter."
                : "Add your first category or let the starter set seed itself."
            }
            action={<Button size="sm" onClick={() => setCreating(true)}>Add category</Button>}
          />
        )}
        {filtered.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Parent</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((category) => (
                <tr key={category.id} className={!category.active ? styles.archivedRow : undefined}>
                  <td>
                    <div className={styles.categoryName}>
                      {category.name}
                      {!category.active && <span className="chip chip-neutral">archived</span>}
                    </div>
                    {category.description && <div className="muted-label">{category.description}</div>}
                  </td>
                  <td>
                    <span className={`chip ${category.type === "income" ? "chip-income" : "chip-expense"}`}>
                      {category.type}
                    </span>
                  </td>
                  <td className="muted-label">
                    {listed.find((parent) => parent.id === category.parent_id)?.name ?? "—"}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="icon-button"
                        title="Edit"
                        onClick={() => setEditing(category)}
                      >
                        <PencilIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        title={category.active ? "Archive" : "Restore"}
                        onClick={() => runToggle(category)}
                      >
                        <ArchiveIcon size={15} />
                      </button>
                      <button
                        type="button"
                        className="icon-button danger"
                        title="Delete"
                        onClick={() => runDelete(category)}
                      >
                        <TrashIcon size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {creating && (
        <CategoryFormModal
          categories={listed}
          onClose={() => setCreating(false)}
          onSaved={onSaved}
        />
      )}
      {editing && (
        <CategoryFormModal
          categories={listed}
          category={editing}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
        />
      )}
    </>
  );
}

interface CategoryFormProps {
  categories: Category[];
  category?: Category;
  onClose: () => void;
  onSaved: () => void;
}

function CategoryFormModal({ categories, category, onClose, onSaved }: CategoryFormProps) {
  const [name, setName] = useState(category?.name ?? "");
  const [type, setType] = useState<CategoryType>(category?.type ?? "expense");
  const [parentId, setParentId] = useState<string>(category?.parent_id ? String(category.parent_id) : "");
  const [description, setDescription] = useState(category?.description ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parents = categories.filter(
    (candidate) => candidate.type === type && candidate.id !== category?.id,
  );

  const submit = () => {
    const payload = {
      name: name.trim(),
      type,
      parent_id: parentId ? Number(parentId) : null,
      description: description.trim() || null,
    };
    setPending(true);
    setError(null);
    const request = category
      ? apiPatch<Category>(`/categories/${category.id}`, payload)
      : apiPost<Category>("/categories", payload);
    request
      .then(() => onSaved())
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setPending(false));
  };

  return (
    <Modal
      title={category ? "Edit category" : "Add category"}
      subtitle="Categories can nest under a parent with the same type."
      onClose={onClose}
    >
      <Field label="Name" hint="required">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="e.g. Groceries"
          autoFocus
        />
      </Field>
      <Field label="Type">
        <Select
          value={type}
          onChange={(event) => {
            setType(event.target.value as CategoryType);
            setParentId("");
          }}
        >
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </Select>
      </Field>
      <Field label="Parent" hint="optional">
        <Select value={parentId} onChange={(event) => setParentId(event.target.value)}>
          <option value="">No parent</option>
          {parents.map((parent) => (
            <option key={parent.id} value={parent.id}>
              {parent.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Description">
        <TextArea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Optional notes"
        />
      </Field>

      <div className={styles.modalActions}>
        <Button variant="ghost" onClick={onClose} disabled={pending}>
          Cancel
        </Button>
        <Button onClick={submit} loading={pending} disabled={!name.trim()}>
          {category ? "Save changes" : "Add category"}
        </Button>
      </div>
      {error && (
        <div className={styles.modalError} role="alert">
          {error}
        </div>
      )}
    </Modal>
  );
}