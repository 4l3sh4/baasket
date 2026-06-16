namespace Baasket.LogisticsV2;

/// <summary>
/// Simulates parcel tracking by advancing the session through timed emoji states:
/// 💳 Paid → 📦 Packed → 🚚 Shipped → ✅ Delivered.
/// </summary>
public sealed class AutomatedTrackingObserver : IObserver, IDisposable
{
    private static readonly CheckoutSessionState[] TrackingSequence =
    [
        CheckoutSessionState.Packed,
        CheckoutSessionState.Shipped,
        CheckoutSessionState.Delivered,
    ];

    private readonly TimeSpan _stepDelay;
    private readonly object _gate = new();
    private readonly Dictionary<Guid, CancellationTokenSource> _activeSimulations = [];

    public AutomatedTrackingObserver(TimeSpan? stepDelay = null)
    {
        _stepDelay = stepDelay ?? TimeSpan.FromSeconds(10);
    }

    public void Update(CheckoutSession session, CheckoutSessionState previousState)
    {
        if (previousState != CheckoutSessionState.CheckoutStarted
            || session.State != CheckoutSessionState.PaymentConfirmed)
        {
            return;
        }

        lock (_gate)
        {
            if (_activeSimulations.ContainsKey(session.SessionId))
                return;

            var cts = new CancellationTokenSource();
            _activeSimulations[session.SessionId] = cts;
            _ = RunSimulationAsync(session, cts.Token);
        }
    }

    private async Task RunSimulationAsync(CheckoutSession session, CancellationToken cancellationToken)
    {
        try
        {
            foreach (var nextState in TrackingSequence)
            {
                await Task.Delay(_stepDelay, cancellationToken).ConfigureAwait(false);
                session.AdvanceTo(nextState);
            }
        }
        catch (OperationCanceledException)
        {
            // Session simulation cancelled — no action required.
        }
        finally
        {
            lock (_gate)
                _activeSimulations.Remove(session.SessionId);
        }
    }

    public void CancelSession(Guid sessionId)
    {
        lock (_gate)
        {
            if (_activeSimulations.TryGetValue(sessionId, out var cts))
            {
                cts.Cancel();
                _activeSimulations.Remove(sessionId);
            }
        }
    }

    public void Dispose()
    {
        lock (_gate)
        {
            foreach (var cts in _activeSimulations.Values)
                cts.Cancel();

            _activeSimulations.Clear();
        }
    }
}
