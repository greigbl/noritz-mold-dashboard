import { JIS_RULE_DESCRIPTIONS } from '@/constants/jis-rules';

type ViolationRulesReferenceProps = {
  descriptions?: Record<string, string>;
};

export function ViolationRulesReference({
  descriptions = JIS_RULE_DESCRIPTIONS,
}: ViolationRulesReferenceProps) {
  const rules = Object.entries(descriptions).sort(
    ([ruleA], [ruleB]) => Number(ruleA) - Number(ruleB)
  );

  return (
    <div className="space-y-2" data-testid="violation-rules-reference">
      <p className="px-1 text-xs font-medium text-sidebar-foreground">違反ルール</p>
      <ul className="space-y-1.5 px-1">
        {rules.map(([rule, description]) => (
          <li key={rule} className="caption-01 text-muted-foreground">
            <span className="font-medium text-sidebar-foreground">{rule}</span>
            <span> : {description}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
