import { Form, Input } from 'antd';
import PasswordStrengthIndicator from './PasswordStrengthIndicator';
import { isStrongEnough } from '../passwordStrength';

const POLICY_MSG =
    'Mínimo 8 caracteres y al menos 2 de: mayúscula y minúscula, un número, un carácter especial';

// Contraseña nueva + confirmación, compartidas por la activación y el cambio propio. La
// política y el visor replican los de mariachi; el backend aplica la misma regla.
export default function NewPasswordFields() {
    const form = Form.useFormInstance();
    const password = Form.useWatch('password', form);
    return (
        <>
            <Form.Item
                label="Contraseña nueva"
                name="password"
                rules={[
                    { required: true, message: 'Ingresa la contraseña nueva' },
                    {
                        validator: (_, value) =>
                            !value || isStrongEnough(value)
                                ? Promise.resolve()
                                : Promise.reject(new Error(POLICY_MSG)),
                    },
                ]}
            >
                <Input.Password autoComplete="new-password" />
            </Form.Item>
            <PasswordStrengthIndicator password={password} />
            <Form.Item
                label="Confirma la contraseña nueva"
                name="confirm"
                dependencies={['password']}
                rules={[
                    { required: true, message: 'Confirma la contraseña nueva' },
                    ({ getFieldValue }) => ({
                        validator: (_, value) =>
                            !value || value === getFieldValue('password')
                                ? Promise.resolve()
                                : Promise.reject(new Error('Las contraseñas no coinciden')),
                    }),
                ]}
            >
                <Input.Password autoComplete="new-password" />
            </Form.Item>
        </>
    );
}
