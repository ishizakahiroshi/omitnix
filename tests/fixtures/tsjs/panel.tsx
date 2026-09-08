/** The customer panel screen. */

export function Panel({ customerId }: { customerId: number }) {
  const reload = () => {
    fetch(`/api/customers/${customerId}`);
  };
  return <button onClick={reload}>Reload</button>;
}
