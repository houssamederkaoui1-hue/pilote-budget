import { useMemo } from "react";
import { useLocation } from "react-router-dom";
import { Badge, Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/States";
import { NAV_ITEMS } from "../lib/navigation";
import styles from "./PlaceholderPage.module.css";

/**
 * Shell page for sections that arrive in later phases. Everything it shows is
 * driven by the shared navigation config, so adding a route stays a one-liner.
 */
export function PlaceholderPage() {
  const location = useLocation();
  const item = useMemo(
    () => NAV_ITEMS.find((nav) => nav.path === location.pathname),
    [location.pathname],
  );

  if (!item) {
    return (
      <Card>
        <EmptyState title="Page not found" description="Use the sidebar to navigate." />
      </Card>
    );
  }

  const Icon = item.icon;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-header__eyebrow">Module</div>
          <h1>{item.label}</h1>
          <p className="page-header__subtitle">{item.description}</p>
        </div>
        <Badge tone={item.status === "ready" ? "positive" : "warning"}>
          {item.status === "ready" ? "Available" : "Next phases"}
        </Badge>
      </div>

      <div className={styles.layout}>
        <Card title="What lands here" subtitle="Planned capabilities for this module" className={styles.main}>
          <ul className={styles.featureList}>
            {item.features.map((feature) => (
              <li key={feature} className={styles.featureItem}>
                <span className={styles.featureDot} aria-hidden />
                {feature}
              </li>
            ))}
          </ul>
        </Card>

        <Card title="Current state" subtitle="Foundation build 0.1.0" className={styles.side}>
          <EmptyState
            icon={<Icon size={20} />}
            title={`${item.label} is scaffolded`}
            description="Schema, services and navigation are in place. Data features arrive in subsequent phases."
          />
        </Card>
      </div>
    </>
  );
}
