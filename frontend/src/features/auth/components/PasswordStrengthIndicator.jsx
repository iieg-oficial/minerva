import { useMemo } from 'react';
import { CheckCircleFilled, MinusCircleOutlined } from '@ant-design/icons';
import { computePasswordStrength } from '../passwordStrength';

const RULE_LABELS = {
    length: 'Mínimo 8 caracteres',
    case: 'Una mayúscula y una minúscula',
    number: 'Al menos un número',
    special: 'Al menos un carácter especial',
};

const SEGMENT_COLORS = ['#e5e7eb', '#f87171', '#fb923c', '#facc15', '#34d399'];

export default function PasswordStrengthIndicator({ password }) {
    const { score, label, rules } = useMemo(
        () => computePasswordStrength(password),
        [password],
    );

    if (!password) return null;
    const fill = SEGMENT_COLORS[score];

    return (
        <div style={{ marginTop: 6, marginBottom: 12 }}>
            <div style={{ display: 'flex', gap: 4 }}>
                {[1, 2, 3, 4].map((i) => (
                    <div
                        key={i}
                        style={{
                            height: 4,
                            flex: 1,
                            borderRadius: 2,
                            background: i <= score ? fill : '#e5e7eb',
                            transition: 'background 0.2s',
                        }}
                    />
                ))}
            </div>
            {label && (
                <div style={{ fontSize: 11, color: '#7C7C7C', marginTop: 4 }}>{label}</div>
            )}
            <ul style={{ marginTop: 6, marginBottom: 0, paddingLeft: 0, listStyle: 'none' }}>
                {Object.entries(RULE_LABELS).map(([key, text]) => (
                    <li
                        key={key}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            fontSize: 12,
                            lineHeight: '20px',
                            color: rules[key] ? '#465055' : '#8E8E8E',
                        }}
                    >
                        {rules[key] ? (
                            <CheckCircleFilled style={{ color: '#10b981', fontSize: 12 }} />
                        ) : (
                            <MinusCircleOutlined style={{ color: '#9ca3af', fontSize: 12 }} />
                        )}
                        <span>{text}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
}
